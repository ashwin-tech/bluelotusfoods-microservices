from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import Optional, List
from app.core.settings import settings
import httpx
import logging
import base64

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/purchase-orders/{po_id}/items")
def get_purchase_order_items(po_id: int):
    """Get line items for a specific purchase order."""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get PO header
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_header_with_estimate'], (po_id,))
                po_header = cur.fetchone()
                if not po_header:
                    raise HTTPException(status_code=404, detail="Purchase order not found")

                # Get PO items
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_items_full'], (po_id,))
                items = [dict(row) for row in cur.fetchall()]

                # Get accepted and rejected ports for this PO
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_port_acceptance'], (po_id,))
                port_rows = cur.fetchall()
                accepted_ports = [r['port_code'] for r in port_rows if r['status'] == 'accepted']
                rejected_ports = [r['port_code'] for r in port_rows if r['status'] == 'rejected']

                po = dict(po_header)
                po['created_at'] = str(po_header['created_at'])
                po['items'] = items
                po['accepted_ports'] = accepted_ports
                po['rejected_ports'] = rejected_ports

                return {"success": True, "purchase_order": po}

        except Exception as e:
            logger.error(f"Error fetching PO items for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


# ─── Box Packaging List (BPL) ───────────────────────────────


class BPLPieceItem(BaseModel):
    piece_number: int
    weight_kg: float


class BPLBoxItem(BaseModel):
    po_item_id: int
    box_number: int
    num_pieces: int = 1
    pieces: List[BPLPieceItem] = []
    # Range mode (cut fillet): pieces is empty, net weight entered directly
    weight_range_from_kg: Optional[float] = None
    weight_range_to_kg: Optional[float] = None
    net_weight_kg: Optional[float] = None  # direct entry for range mode


class SaveBPLRequest(BaseModel):
    po_id: int
    port_code: str
    status: str = "draft"  # "draft" or "completed"
    notes: Optional[str] = None
    invoice_number: Optional[str] = None
    air_way_bill: Optional[str] = None
    packed_date: Optional[str] = None      # YYYY-MM-DD
    expiry_date: Optional[str] = None      # YYYY-MM-DD
    po_item_ids: List[int]  # which PO items are selected for this port
    boxes: List[BPLBoxItem]


class POStatusTransitionRequest(BaseModel):
    actor_role: str        # 'vendor', 'buyer', or 'system'
    actor_name: str
    actor_code: str
    notes: Optional[str] = None


class PortAcceptRequest(BaseModel):
    actor_name: str
    actor_code: str
    notes: Optional[str] = None


def _transition_po_status(cur, po_id: int, allowed_from: list, new_status: str,
                           actor_role: str, actor_name: str, actor_code: str,
                           notes: Optional[str] = None) -> str:
    """
    Row-locked status transition with audit trail.
    Returns the old status. Raises HTTPException if transition is not allowed.
    """
    cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_for_update'], (po_id,))
    po = cur.fetchone()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    current_status = po['status']
    if current_status not in allowed_from:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current_status}' to '{new_status}'. "
                   f"Allowed from: {allowed_from}"
        )

    cur.execute(DatabaseQueries.PURCHASE_ORDERS['update_status'], (new_status, po_id))
    cur.execute(
        DatabaseQueries.PURCHASE_ORDERS['insert_audit'],
        (po_id, current_status, new_status, actor_role, actor_name, actor_code, notes)
    )
    return current_status


@router.get("/purchase-orders/{po_id}/bpl")
def get_bpl_for_po(po_id: int):
    """
    Get all box packaging lists for a PO, grouped by port.
    Also returns which po_item_ids already have BPL entries.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get all BPLs for this PO
                cur.execute(DatabaseQueries.BPL['get_for_po'], (po_id,))
                bpls = [dict(r) for r in cur.fetchall()]

                for bpl in bpls:
                    bpl['created_at'] = str(bpl['created_at'])
                    bpl['updated_at'] = str(bpl['updated_at'])
                    bpl['packed_date'] = str(bpl['packed_date']) if bpl.get('packed_date') else None
                    bpl['expiry_date'] = str(bpl['expiry_date']) if bpl.get('expiry_date') else None
                    # Get boxes for each BPL
                    cur.execute(DatabaseQueries.BPL['get_boxes'], (bpl['id'],))
                    boxes = [dict(r) for r in cur.fetchall()]

                    # Fetch pieces for each box
                    for box in boxes:
                        cur.execute(DatabaseQueries.BPL['get_pieces'], (box['id'],))
                        box['pieces'] = [dict(p) for p in cur.fetchall()]

                    bpl['boxes'] = boxes

                # Get set of po_item_ids that have BPL entries (for the green-check indicator)
                cur.execute(DatabaseQueries.BPL['get_covered_items'], (po_id,))
                covered_item_ids = [r['po_item_id'] for r in cur.fetchall()]

                return {
                    "success": True,
                    "bpls": bpls,
                    "covered_po_item_ids": covered_item_ids,
                }

        except Exception as e:
            logger.error(f"Error fetching BPLs for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-orders/bpl/save")
def save_bpl(request: SaveBPLRequest):
    """
    Save (create or update) a box packaging list for a PO + port.
    If a BPL already exists for this PO+port, it is updated (boxes replaced).
    Prevents duplicate: one BPL per PO+port enforced.
    """
    if not request.boxes:
        raise HTTPException(status_code=400, detail="At least one box entry is required")

    # Validate that all box po_item_ids are in the selected items list
    box_item_ids = set(b.po_item_id for b in request.boxes)
    selected_ids = set(request.po_item_ids)
    if not box_item_ids.issubset(selected_ids):
        raise HTTPException(
            status_code=400,
            detail="All box entries must reference selected PO items"
        )

    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Guard: BPL creation/update only allowed when this port has been accepted
                cur.execute(DatabaseQueries.BPL['check_port_accepted'], (request.po_id, request.port_code))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Port '{request.port_code}' has not been accepted for this PO"
                    )
                # Also guard against creating BPL on rejected/cancelled POs
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_status'], (request.po_id,))
                po_row = cur.fetchone()
                if not po_row:
                    raise HTTPException(status_code=404, detail="Purchase order not found")
                if po_row['status'] in ('rejected', 'cancelled'):
                    raise HTTPException(
                        status_code=400,
                        detail=f"BPL not allowed for PO with status '{po_row['status']}'"
                    )

                # Check if BPL already exists for this PO+port
                cur.execute(DatabaseQueries.BPL['get_by_po_port'], (request.po_id, request.port_code))
                existing = cur.fetchone()

                if existing:
                    bpl_id = existing['id']
                    # Update status/notes + header fields
                    cur.execute(
                        DatabaseQueries.BPL['update'],
                        (request.status, request.notes,
                         request.invoice_number, request.air_way_bill,
                         request.packed_date, request.expiry_date,
                         bpl_id)
                    )
                    # Delete old boxes and re-insert
                    cur.execute(DatabaseQueries.BPL['delete_items'], (bpl_id,))
                else:
                    # Create new BPL
                    cur.execute(
                        DatabaseQueries.BPL['insert'],
                        (request.po_id, request.port_code, request.status, request.notes,
                         request.invoice_number, request.air_way_bill,
                         request.packed_date, request.expiry_date)
                    )
                    bpl_id = cur.fetchone()['id']

                # Insert box items + their pieces
                for box in request.boxes:
                    # Range mode: pieces is empty, net weight entered directly
                    if box.pieces:
                        net_wt = sum(p.weight_kg for p in box.pieces)
                    else:
                        net_wt = box.net_weight_kg or 0
                    cur.execute(
                        DatabaseQueries.BPL['insert_item'],
                        (bpl_id, box.po_item_id, box.box_number, box.num_pieces,
                         box.num_pieces, net_wt, net_wt,
                         box.weight_range_from_kg, box.weight_range_to_kg)
                    )
                    bpl_item_id = cur.fetchone()['id']

                    # Insert individual pieces (skipped for range mode)
                    for piece in box.pieces:
                        cur.execute(
                            DatabaseQueries.BPL['insert_piece'],
                            (bpl_item_id, piece.piece_number, piece.weight_kg)
                        )

                conn.commit()

                logger.info(f"Saved BPL {bpl_id} for PO {request.po_id} port {request.port_code} "
                            f"with {len(request.boxes)} boxes (status={request.status})")

                return {
                    "success": True,
                    "bpl_id": bpl_id,
                    "status": request.status,
                    "box_count": len(request.boxes),
                }

        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving BPL: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/{vendor_code}")
def get_vendor(vendor_code: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.VENDORS['get_by_code'], (vendor_code,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row


@router.get("/{vendor_id}/purchase-orders")
def get_vendor_purchase_orders(vendor_id: int, week_start: Optional[str] = Query(None)):
    """
    Get all purchase orders for a vendor, optionally filtered by week.
    week_start should be a Monday date (YYYY-MM-DD). If provided, returns POs
    created between week_start and week_start + 6 days.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if week_start:
                    cur.execute(
                        DatabaseQueries.PURCHASE_ORDERS['get_vendor_pos_by_week'],
                        (vendor_id, week_start, week_start)
                    )
                else:
                    cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_vendor_pos_all'], (vendor_id,))

                rows = cur.fetchall()
                pos = []
                for row in rows:
                    po = dict(row)
                    po['created_at'] = str(row['created_at'])
                    pos.append(po)

                return {"success": True, "purchase_orders": pos}

        except Exception as e:
            logger.error(f"Error fetching POs for vendor {vendor_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


# ─── BPL Send Email ─────────────────────────────────────────


@router.post("/purchase-orders/{po_id}/bpl/{port_code}/send-email")
async def send_bpl_email(po_id: int, port_code: str):
    """
    Gather BPL data + vendor info for a PO/port, then call the
    email service to send branded PDF to owner and plain PDF to vendor.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1) Get PO header + vendor info
                cur.execute(DatabaseQueries.BPL['get_po_for_email'], (po_id,))
                po_row = cur.fetchone()
                if not po_row:
                    raise HTTPException(status_code=404, detail="Purchase order not found")

                # 2) Get BPL header for this PO + port
                cur.execute(DatabaseQueries.BPL['get_header'], (po_id, port_code))
                bpl_row = cur.fetchone()
                if not bpl_row:
                    raise HTTPException(status_code=404, detail="No BPL found for this PO and port")

                bpl_id = bpl_row['id']
                is_upload_mode = bool(bpl_row.get('uploaded_file_path'))

                if is_upload_mode:
                    # Upload mode: fetch file from GCS and forward as attachment
                    email_payload = {
                        "po_number": po_row['po_number'],
                        "port_code": port_code,
                        "vendor_name": po_row['vendor_name'],
                        "vendor_email": po_row['vendor_email'] or "",
                        "vendor_country": po_row['vendor_country'] or "",
                        "owner_email": settings.owner_notification_email,
                        "invoice_number": bpl_row['invoice_number'] or "",
                        "air_way_bill": bpl_row['air_way_bill'] or "",
                        "packed_date": str(bpl_row['packed_date']) if bpl_row.get('packed_date') else "",
                        "expiry_date": str(bpl_row['expiry_date']) if bpl_row.get('expiry_date') else "",
                        "attachment_filename": bpl_row['uploaded_file_name'],
                    }
                    try:
                        from google.cloud import storage as gcs_storage
                        gcs_client = gcs_storage.Client()
                        bucket = gcs_client.bucket(settings.gcs_bucket_name)
                        blob = bucket.blob(bpl_row['uploaded_file_path'])
                        file_bytes = blob.download_as_bytes()
                        email_payload["attachment_bytes"] = base64.b64encode(file_bytes).decode('utf-8')
                        logger.info(f"Fetched BPL file from GCS for email: {bpl_row['uploaded_file_path']} ({len(file_bytes)} bytes)")
                    except Exception as gcs_err:
                        logger.error(f"GCS download failed: {gcs_err}")
                        raise HTTPException(status_code=500, detail=f"Failed to fetch uploaded file: {str(gcs_err)}")

                    email_endpoint = f"{settings.email_service_url}/email/bpl/send-uploaded"
                    logger.info(f"📧 Sending uploaded BPL email for PO {po_row['po_number']} port {port_code}")
                else:
                    # Manual mode: build structured data payload for PDF generation
                    # 3) Get BPL items (boxes) joined to PO item details
                    cur.execute(DatabaseQueries.BPL['get_items_for_email'], (bpl_id,))
                    box_rows = [dict(r) for r in cur.fetchall()]

                    # 4) Fetch pieces for each box
                    for box in box_rows:
                        cur.execute(DatabaseQueries.BPL['get_pieces_for_email'], (box['bpl_item_id'],))
                        box['pieces'] = [dict(p) for p in cur.fetchall()]

                    # 5) Group boxes by PO item (species line)
                    items_map = {}
                    for box in box_rows:
                        key = box['po_item_id']
                        if key not in items_map:
                            items_map[key] = {
                                "fish_name": box['fish_name'],
                                "cut_name": box['cut_name'],
                                "grade_name": box['grade_name'],
                                "fish_size": box['fish_size'],
                                "order_weight_kg": float(box['order_weight_kg']) if box.get('order_weight_kg') else 0,
                                "boxes": [],
                            }
                        total_weight = sum(
                            float(p['weight_kg']) for p in box['pieces']
                        ) if box['pieces'] else (float(box['net_weight_kg']) if box.get('net_weight_kg') else 0)

                        items_map[key]["boxes"].append({
                            "box_number": box['box_number'],
                            "num_pieces": box['num_pieces'],
                            "net_weight_kg": total_weight,
                            "weight_range_from_kg": float(box['weight_range_from_kg']) if box.get('weight_range_from_kg') is not None else None,
                            "weight_range_to_kg": float(box['weight_range_to_kg']) if box.get('weight_range_to_kg') is not None else None,
                            "pieces": [
                                {"piece_number": p['piece_number'], "weight_kg": float(p['weight_kg'])}
                                for p in box['pieces']
                            ],
                        })

                    items_list = list(items_map.values())
                    total_boxes = sum(len(item['boxes']) for item in items_list)

                    email_payload = {
                        "po_number": po_row['po_number'],
                        "port_code": port_code,
                        "vendor_name": po_row['vendor_name'],
                        "vendor_email": po_row['vendor_email'] or "",
                        "vendor_country": po_row['vendor_country'] or "",
                        "owner_email": settings.owner_notification_email,
                        "invoice_number": bpl_row['invoice_number'] or "",
                        "air_way_bill": bpl_row['air_way_bill'] or "",
                        "packed_date": str(bpl_row['packed_date']) if bpl_row.get('packed_date') else "",
                        "expiry_date": str(bpl_row['expiry_date']) if bpl_row.get('expiry_date') else "",
                        "total_boxes": total_boxes,
                        "items": items_list,
                    }
                    email_endpoint = f"{settings.email_service_url}/email/bpl/send-emails"
                    logger.info(f"📧 Sending BPL email for PO {po_row['po_number']} port {port_code}")

                logger.info(f"   Vendor: {po_row['vendor_name']} ({po_row['vendor_email']})")
                logger.info(f"   Email service: {settings.email_service_url}, upload_mode={is_upload_mode}")

            # 7) Call email service (outside the DB cursor context)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    email_endpoint,
                    json=email_payload,
                    timeout=60.0,
                )

                if response.status_code != 200:
                    logger.error(f"❌ Email service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Email service error: {response.text}",
                    )

                email_result = response.json()
                logger.info(f"✅ BPL email sent: {email_result}")

                # 8) Update BPL status to 'sent' in DB, then check for auto-fulfill
                if email_result.get("success"):
                    with get_conn() as conn2:
                        try:
                            with conn2.cursor(cursor_factory=RealDictCursor) as cur2:
                                cur2.execute(DatabaseQueries.BPL['update_status_sent'], (po_id, port_code))
                                logger.info(f"Updated BPL status to 'sent' for PO {po_id} port {port_code}")

                                # Auto-fulfill: if all accepted ports now have a sent/completed BPL → fulfill
                                cur2.execute(DatabaseQueries.BPL['get_accepted_port_count'], (po_id,))
                                accepted_count = cur2.fetchone()['cnt']

                                cur2.execute(DatabaseQueries.BPL['get_sent_bpl_count'], (po_id,))
                                sent_count = cur2.fetchone()['cnt']

                                if accepted_count > 0 and sent_count >= accepted_count:
                                    try:
                                        _transition_po_status(
                                            cur2, po_id,
                                            allowed_from=['accepted'],
                                            new_status='fulfilled',
                                            actor_role='system',
                                            actor_name='system',
                                            actor_code='auto'
                                        )
                                        logger.info(f"PO {po_id} auto-fulfilled: all {accepted_count} accepted port(s) sent")
                                    except HTTPException as te:
                                        # Non-fatal: PO might already be fulfilled or in unexpected state
                                        logger.warning(f"Auto-fulfill skipped for PO {po_id}: {te.detail}")

                                conn2.commit()
                        except Exception as db_err:
                            logger.error(f"Failed to update BPL status: {db_err}")

                return {
                    "success": email_result.get("success", True),
                    "message": email_result.get("message", "BPL emails sent"),
                }

        except httpx.RequestError as e:
            logger.error(f"Email service connection error: {str(e)}")
            raise HTTPException(status_code=503, detail="Email service unavailable")
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            logger.error(f"Error sending BPL email: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))


# ─── PO Status Workflow ──────────────────────────────────────


@router.post("/purchase-orders/{po_id}/accept")
def accept_purchase_order(po_id: int, request: POStatusTransitionRequest):
    """Vendor accepts a purchase order. Only allowed from 'sent' status."""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _transition_po_status(
                    cur, po_id,
                    allowed_from=['sent'],
                    new_status='accepted',
                    actor_role='vendor',
                    actor_name=request.actor_name,
                    actor_code=request.actor_code,
                    notes=request.notes,
                )
                conn.commit()
                logger.info(f"PO {po_id} accepted by vendor {request.actor_code}")
                return {"success": True, "po_id": po_id, "status": "accepted"}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error accepting PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-orders/{po_id}/reject")
def reject_purchase_order(po_id: int, request: POStatusTransitionRequest):
    """Vendor rejects a purchase order. Only allowed from 'sent' status."""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _transition_po_status(
                    cur, po_id,
                    allowed_from=['sent'],
                    new_status='rejected',
                    actor_role='vendor',
                    actor_name=request.actor_name,
                    actor_code=request.actor_code,
                    notes=request.notes,
                )
                conn.commit()
                logger.info(f"PO {po_id} rejected by vendor {request.actor_code}")
                return {"success": True, "po_id": po_id, "status": "rejected"}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error rejecting PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


def _get_port_lists(cur, po_id: int) -> tuple:
    """Return (accepted_ports, rejected_ports) for a PO."""
    cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_port_acceptance'], (po_id,))
    rows = cur.fetchall()
    return (
        [r['port_code'] for r in rows if r['status'] == 'accepted'],
        [r['port_code'] for r in rows if r['status'] == 'rejected'],
    )


@router.post("/purchase-orders/{po_id}/ports/{port_code}/accept")
def accept_port(po_id: int, port_code: str, request: PortAcceptRequest):
    """
    Vendor accepts a specific port. Toggleable — can flip a rejected port back to accepted.
    Transitions PO from 'sent' → 'accepted' on first port acceptance.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_for_update'], (po_id,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found")
                if po['status'] in ('rejected', 'cancelled'):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot accept port on a '{po['status']}' PO"
                    )

                # Upsert port with status = 'accepted'
                cur.execute(
                    DatabaseQueries.PURCHASE_ORDERS['upsert_port_acceptance'],
                    (po_id, port_code, 'accepted', request.actor_name, request.actor_code, request.notes)
                )

                # Transition PO status based on current state
                if po['status'] == 'sent':
                    # First acceptance — move to accepted
                    cur.execute(DatabaseQueries.PURCHASE_ORDERS['update_status'], ('accepted', po_id))
                    cur.execute(
                        DatabaseQueries.PURCHASE_ORDERS['insert_audit'],
                        (po_id, 'sent', 'accepted', 'vendor', request.actor_name, request.actor_code,
                         f"Port {port_code} accepted")
                    )
                elif po['status'] == 'fulfilled':
                    # New port accepted after fulfill — revert to accepted (new port has no BPL yet)
                    cur.execute(DatabaseQueries.PURCHASE_ORDERS['update_status'], ('accepted', po_id))
                    cur.execute(
                        DatabaseQueries.PURCHASE_ORDERS['insert_audit'],
                        (po_id, 'fulfilled', 'accepted', 'vendor', request.actor_name, request.actor_code,
                         f"Port {port_code} accepted — awaiting BPL")
                    )

                accepted_ports, rejected_ports = _get_port_lists(cur, po_id)
                conn.commit()
                logger.info(f"Port {port_code} accepted for PO {po_id} by {request.actor_code}")
                return {"success": True, "po_id": po_id, "port_code": port_code,
                        "accepted_ports": accepted_ports, "rejected_ports": rejected_ports}

        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error accepting port {port_code} for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-orders/{po_id}/ports/{port_code}/reject")
def reject_port(po_id: int, port_code: str, request: PortAcceptRequest):
    """
    Vendor rejects a specific port. Toggleable — can flip an accepted port to rejected.
    If no accepted ports remain and PO is 'accepted', reverts PO back to 'sent'.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_for_update'], (po_id,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found")
                if po['status'] in ('rejected', 'cancelled', 'fulfilled'):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot change port status on a '{po['status']}' PO"
                    )

                # Upsert port with status = 'rejected'
                cur.execute(
                    DatabaseQueries.PURCHASE_ORDERS['upsert_port_acceptance'],
                    (po_id, port_code, 'rejected', request.actor_name, request.actor_code, request.notes)
                )

                # If PO is 'accepted', check remaining accepted ports
                if po['status'] == 'accepted':
                    cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_remaining_accepted_ports'], (po_id,))
                    remaining = cur.fetchone()['cnt']
                    if remaining == 0:
                        # No accepted ports left — revert to 'sent'
                        cur.execute(DatabaseQueries.PURCHASE_ORDERS['update_status'], ('sent', po_id))
                        cur.execute(
                            DatabaseQueries.PURCHASE_ORDERS['insert_audit'],
                            (po_id, 'accepted', 'sent', 'vendor', request.actor_name, request.actor_code,
                             "All ports rejected — PO reverted to received")
                        )
                    else:
                        # Check if all remaining accepted ports already have sent/completed BPLs
                        cur.execute(DatabaseQueries.BPL['get_sent_bpl_count'], (po_id,))
                        sent_count = cur.fetchone()['cnt']
                        if sent_count >= remaining:
                            # All remaining accepted ports have sent BPLs → re-fulfill
                            cur.execute(DatabaseQueries.PURCHASE_ORDERS['update_status'], ('fulfilled', po_id))
                            cur.execute(
                                DatabaseQueries.PURCHASE_ORDERS['insert_audit'],
                                (po_id, 'accepted', 'fulfilled', 'system', 'system', 'auto',
                                 f"Port {port_code} rejected — all remaining accepted ports already sent")
                            )

                accepted_ports, rejected_ports = _get_port_lists(cur, po_id)
                conn.commit()
                logger.info(f"Port {port_code} rejected for PO {po_id} by {request.actor_code}")
                return {"success": True, "po_id": po_id, "port_code": port_code,
                        "accepted_ports": accepted_ports, "rejected_ports": rejected_ports}

        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error rejecting port {port_code} for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


class ManualFulfillRequest(BaseModel):
    actor_name: str
    actor_code: str


@router.post("/purchase-orders/{po_id}/fulfill")
def manually_fulfill_po(po_id: int, request: ManualFulfillRequest):
    """
    Vendor manually marks a PO as fulfilled without requiring a BPL.
    For vendors who manage shipping details outside the portal.
    Overrides the normal BPL-based auto-fulfill flow.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _transition_po_status(
                    cur, po_id,
                    allowed_from=['accepted'],
                    new_status='fulfilled',
                    actor_role='vendor',
                    actor_name=request.actor_name,
                    actor_code=request.actor_code,
                    notes='Manually marked fulfilled by vendor (no BPL)',
                )
                conn.commit()
                logger.info(f"PO {po_id} manually fulfilled by vendor {request.actor_code}")
                return {"success": True, "po_id": po_id, "po_status": "fulfilled"}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error manually fulfilling PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/purchase-orders/{po_id}/timeline")
def get_po_timeline(po_id: int):
    """
    Return key timestamps for the PO lifecycle:
    created_at, first accepted_at, and fulfilled_at.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_created_at'], (po_id,))
                po = cur.fetchone()
                if not po:
                    raise HTTPException(status_code=404, detail="Purchase order not found")

                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_audit_timestamps'], (po_id,))
                row = cur.fetchone()

                return {
                    "success": True,
                    "created_at": str(po['created_at']),
                    "accepted_at": str(row['accepted_at']) if row['accepted_at'] else None,
                    "fulfilled_at": str(row['fulfilled_at']) if row['fulfilled_at'] else None,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching timeline for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase-orders/bpl/upload")
async def upload_bpl_file(
    po_id: int = Form(...),
    port_code: str = Form(...),
    invoice_number: Optional[str] = Form(None),
    air_way_bill: Optional[str] = Form(None),
    packed_date: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    """
    Upload a BPL document (PDF/Excel/image) for a PO + port.
    The file is stored in GCS and the path saved in the DB.
    The BPL is immediately marked as 'completed'.
    """
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Guard: port must be accepted
                cur.execute(DatabaseQueries.BPL['check_port_accepted'], (po_id, port_code))
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Port '{port_code}' has not been accepted for this PO"
                    )
                # Guard: PO must not be rejected/cancelled
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_status'], (po_id,))
                po_row = cur.fetchone()
                if not po_row:
                    raise HTTPException(status_code=404, detail="Purchase order not found")
                if po_row['status'] in ('rejected', 'cancelled'):
                    raise HTTPException(
                        status_code=400,
                        detail=f"BPL upload not allowed for PO with status '{po_row['status']}'"
                    )

                # Read file bytes and upload to GCS
                file_bytes = await file.read()
                original_name = file.filename or "bpl_upload"
                gcs_path = f"bpl/{po_id}/{port_code}/{original_name}"

                try:
                    from google.cloud import storage as gcs_storage
                    gcs_client = gcs_storage.Client()
                    bucket = gcs_client.bucket(settings.gcs_bucket_name)
                    blob = bucket.blob(gcs_path)
                    blob.upload_from_string(file_bytes, content_type=file.content_type or 'application/octet-stream')
                    logger.info(f"Uploaded BPL file to GCS: gs://{settings.gcs_bucket_name}/{gcs_path}")
                except Exception as gcs_err:
                    logger.error(f"GCS upload failed: {gcs_err}")
                    raise HTTPException(status_code=500, detail=f"File storage failed: {str(gcs_err)}")

                # Upsert BPL row
                cur.execute(DatabaseQueries.BPL['get_by_po_port'], (po_id, port_code))
                existing = cur.fetchone()

                if existing:
                    bpl_id = existing['id']
                    cur.execute(
                        DatabaseQueries.BPL['update_upload'],
                        (gcs_path, original_name,
                         invoice_number, air_way_bill,
                         packed_date, expiry_date, notes,
                         bpl_id)
                    )
                    # Clear any existing box entries (switching from manual to upload)
                    cur.execute(DatabaseQueries.BPL['delete_items'], (bpl_id,))
                else:
                    cur.execute(
                        DatabaseQueries.BPL['insert_upload'],
                        (po_id, port_code, gcs_path, original_name,
                         invoice_number, air_way_bill, packed_date, expiry_date, notes)
                    )
                    bpl_id = cur.fetchone()['id']

                conn.commit()
                logger.info(f"Saved upload BPL {bpl_id} for PO {po_id} port {port_code}: {original_name}")
                return {"success": True, "bpl_id": bpl_id, "file_name": original_name, "status": "completed"}

        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error uploading BPL: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/purchase-orders/{po_id}/audit")
def get_po_audit(po_id: int):
    """Get the audit trail for a purchase order."""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_created_at'], (po_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Purchase order not found")

                cur.execute(DatabaseQueries.PURCHASE_ORDERS['get_audit_records'], (po_id,))
                rows = cur.fetchall()
                audit = []
                for row in rows:
                    entry = dict(row)
                    entry['created_at'] = str(row['created_at'])
                    audit.append(entry)

                return {"success": True, "audit": audit}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching audit for PO {po_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
