from fastapi import APIRouter, HTTPException, Query
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import Optional, List
from app.core.settings import settings
import httpx
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/purchase-orders/{po_id}/items")
def get_purchase_order_items(po_id: int):
    """Get line items for a specific purchase order."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get PO header
            cur.execute("""
                SELECT
                    po.id, po.po_number, po.quote_id, po.estimate_id,
                    po.vendor_id, po.status, po.created_at,
                    be.estimate_number
                FROM purchase_order po
                JOIN buyer_estimate be ON po.estimate_id = be.id
                WHERE po.id = %s
            """, (po_id,))
            po_header = cur.fetchone()
            if not po_header:
                raise HTTPException(status_code=404, detail="Purchase order not found")

            # Get PO items
            cur.execute("""
                SELECT
                    id, fish_name, cut_name, grade_name, fish_size,
                    port_code, destination_name, price_per_kg,
                    airfreight_per_kg, total_per_kg,
                    order_weight_lbs, order_weight_kg
                FROM purchase_order_item
                WHERE po_id = %s
                ORDER BY port_code, fish_name
            """, (po_id,))
            items = [dict(row) for row in cur.fetchall()]

            # Get accepted and rejected ports for this PO
            cur.execute("""
                SELECT port_code, status FROM purchase_order_port_acceptance
                WHERE po_id = %s ORDER BY port_code
            """, (po_id,))
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
    finally:
        release_connection(conn)


# ─── Box Packaging List (BPL) ───────────────────────────────


class BPLPieceItem(BaseModel):
    piece_number: int
    weight_kg: float


class BPLBoxItem(BaseModel):
    po_item_id: int
    box_number: int
    num_pieces: int = 1
    pieces: List[BPLPieceItem] = []
    # net_weight_kg is auto-computed from sum of piece weights
    # gross_weight_kg is optional (for legacy compat)


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
    cur.execute(
        "SELECT id, status FROM purchase_order WHERE id = %s FOR UPDATE",
        (po_id,)
    )
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

    cur.execute(
        "UPDATE purchase_order SET status = %s, updated_at = NOW() WHERE id = %s",
        (new_status, po_id)
    )
    cur.execute(
        """
        INSERT INTO purchase_order_audit
            (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (po_id, current_status, new_status, actor_role, actor_name, actor_code, notes)
    )
    return current_status


@router.get("/purchase-orders/{po_id}/bpl")
def get_bpl_for_po(po_id: int):
    """
    Get all box packaging lists for a PO, grouped by port.
    Also returns which po_item_ids already have BPL entries.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all BPLs for this PO
            cur.execute("""
                SELECT id, po_id, port_code, status, notes,
                       invoice_number, air_way_bill, packed_date, expiry_date,
                       created_at, updated_at
                FROM box_packaging_list
                WHERE po_id = %s
                ORDER BY port_code
            """, (po_id,))
            bpls = [dict(r) for r in cur.fetchall()]

            for bpl in bpls:
                bpl['created_at'] = str(bpl['created_at'])
                bpl['updated_at'] = str(bpl['updated_at'])
                bpl['packed_date'] = str(bpl['packed_date']) if bpl.get('packed_date') else None
                bpl['expiry_date'] = str(bpl['expiry_date']) if bpl.get('expiry_date') else None
                # Get boxes for each BPL
                cur.execute("""
                    SELECT
                        bi.id, bi.po_item_id, bi.box_number, bi.num_pieces,
                        bi.net_weight_kg, bi.gross_weight_kg,
                        poi.fish_name, poi.cut_name, poi.grade_name, poi.fish_size
                    FROM box_packaging_list_item bi
                    JOIN purchase_order_item poi ON bi.po_item_id = poi.id
                    WHERE bi.bpl_id = %s
                    ORDER BY bi.box_number
                """, (bpl['id'],))
                boxes = [dict(r) for r in cur.fetchall()]

                # Fetch pieces for each box
                for box in boxes:
                    cur.execute("""
                        SELECT id, piece_number, weight_kg
                        FROM box_packaging_list_piece
                        WHERE bpl_item_id = %s
                        ORDER BY piece_number
                    """, (box['id'],))
                    box['pieces'] = [dict(p) for p in cur.fetchall()]

                bpl['boxes'] = boxes

            # Get set of po_item_ids that have BPL entries (for the green-check indicator)
            cur.execute("""
                SELECT DISTINCT bi.po_item_id
                FROM box_packaging_list_item bi
                JOIN box_packaging_list bpl ON bi.bpl_id = bpl.id
                WHERE bpl.po_id = %s
            """, (po_id,))
            covered_item_ids = [r['po_item_id'] for r in cur.fetchall()]

            return {
                "success": True,
                "bpls": bpls,
                "covered_po_item_ids": covered_item_ids,
            }

    except Exception as e:
        logger.error(f"Error fetching BPLs for PO {po_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_connection(conn)


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

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Guard: BPL creation/update only allowed when this port has been accepted
            cur.execute(
                "SELECT id FROM purchase_order_port_acceptance WHERE po_id = %s AND port_code = %s AND status = 'accepted'",
                (request.po_id, request.port_code)
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"Port '{request.port_code}' has not been accepted for this PO"
                )
            # Also guard against creating BPL on rejected/cancelled POs
            cur.execute("SELECT status FROM purchase_order WHERE id = %s", (request.po_id,))
            po_row = cur.fetchone()
            if not po_row:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            if po_row['status'] in ('rejected', 'cancelled'):
                raise HTTPException(
                    status_code=400,
                    detail=f"BPL not allowed for PO with status '{po_row['status']}'"
                )

            # Check if BPL already exists for this PO+port
            cur.execute("""
                SELECT id FROM box_packaging_list
                WHERE po_id = %s AND port_code = %s
            """, (request.po_id, request.port_code))
            existing = cur.fetchone()

            if existing:
                bpl_id = existing['id']
                # Update status/notes + header fields
                cur.execute("""
                    UPDATE box_packaging_list
                    SET status = %s, notes = %s,
                        invoice_number = %s, air_way_bill = %s,
                        packed_date = %s, expiry_date = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """, (request.status, request.notes,
                      request.invoice_number, request.air_way_bill,
                      request.packed_date, request.expiry_date,
                      bpl_id))
                # Delete old boxes and re-insert
                cur.execute("DELETE FROM box_packaging_list_item WHERE bpl_id = %s", (bpl_id,))
            else:
                # Create new BPL
                cur.execute("""
                    INSERT INTO box_packaging_list
                        (po_id, port_code, status, notes,
                         invoice_number, air_way_bill, packed_date, expiry_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (request.po_id, request.port_code, request.status, request.notes,
                      request.invoice_number, request.air_way_bill,
                      request.packed_date, request.expiry_date))
                bpl_id = cur.fetchone()['id']

            # Insert box items + their pieces
            for box in request.boxes:
                # net_weight = sum of piece weights
                net_wt = sum(p.weight_kg for p in box.pieces) if box.pieces else 0
                cur.execute("""
                    INSERT INTO box_packaging_list_item
                        (bpl_id, po_item_id, box_number, box_count, num_pieces,
                         net_weight_kg, gross_weight_kg)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (bpl_id, box.po_item_id, box.box_number, box.num_pieces,
                      box.num_pieces, net_wt, net_wt))
                bpl_item_id = cur.fetchone()['id']

                # Insert individual pieces
                for piece in box.pieces:
                    cur.execute("""
                        INSERT INTO box_packaging_list_piece
                            (bpl_item_id, piece_number, weight_kg)
                        VALUES (%s, %s, %s)
                    """, (bpl_item_id, piece.piece_number, piece.weight_kg))

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
    finally:
        release_connection(conn)


@router.get("/{vendor_code}")
def get_vendor(vendor_code: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.VENDORS['get_by_code'], (vendor_code,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row
    finally:
        release_connection(conn)


@router.get("/{vendor_id}/purchase-orders")
def get_vendor_purchase_orders(vendor_id: int, week_start: Optional[str] = Query(None)):
    """
    Get all purchase orders for a vendor, optionally filtered by week.
    week_start should be a Monday date (YYYY-MM-DD). If provided, returns POs
    created between week_start and week_start + 6 days.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if week_start:
                cur.execute("""
                    SELECT
                        po.id, po.po_number, po.quote_id, po.estimate_id,
                        po.vendor_id, po.status, po.created_at,
                        be.estimate_number,
                        (SELECT COUNT(*) FROM purchase_order_item poi WHERE poi.po_id = po.id) as item_count
                    FROM purchase_order po
                    JOIN buyer_estimate be ON po.estimate_id = be.id
                    WHERE po.vendor_id = %s
                      AND po.created_at >= %s::date
                      AND po.created_at < (%s::date + INTERVAL '7 days')
                    ORDER BY po.created_at DESC
                """, (vendor_id, week_start, week_start))
            else:
                cur.execute("""
                    SELECT
                        po.id, po.po_number, po.quote_id, po.estimate_id,
                        po.vendor_id, po.status, po.created_at,
                        be.estimate_number,
                        (SELECT COUNT(*) FROM purchase_order_item poi WHERE poi.po_id = po.id) as item_count
                    FROM purchase_order po
                    JOIN buyer_estimate be ON po.estimate_id = be.id
                    WHERE po.vendor_id = %s
                    ORDER BY po.created_at DESC
                    LIMIT 50
                """, (vendor_id,))

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
    finally:
        release_connection(conn)


# ─── BPL Send Email ─────────────────────────────────────────


@router.post("/purchase-orders/{po_id}/bpl/{port_code}/send-email")
async def send_bpl_email(po_id: int, port_code: str):
    """
    Gather BPL data + vendor info for a PO/port, then call the
    email service to send branded PDF to owner and plain PDF to vendor.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1) Get PO header + vendor info
            cur.execute("""
                SELECT
                    po.id, po.po_number, po.vendor_id,
                    v.name AS vendor_name,
                    v.contact_email AS vendor_email,
                    v.country AS vendor_country
                FROM purchase_order po
                JOIN vendors v ON po.vendor_id = v.id
                WHERE po.id = %s
            """, (po_id,))
            po_row = cur.fetchone()
            if not po_row:
                raise HTTPException(status_code=404, detail="Purchase order not found")

            # 2) Get BPL header for this PO + port
            cur.execute("""
                SELECT id, invoice_number, air_way_bill, packed_date, expiry_date
                FROM box_packaging_list
                WHERE po_id = %s AND port_code = %s
            """, (po_id, port_code))
            bpl_row = cur.fetchone()
            if not bpl_row:
                raise HTTPException(status_code=404, detail="No BPL found for this PO and port")

            bpl_id = bpl_row['id']

            # 3) Get BPL items (boxes) joined to PO item details
            cur.execute("""
                SELECT
                    bi.id AS bpl_item_id, bi.po_item_id, bi.box_number, bi.num_pieces,
                    bi.net_weight_kg,
                    poi.fish_name, poi.cut_name, poi.grade_name, poi.fish_size,
                    poi.order_weight_kg
                FROM box_packaging_list_item bi
                JOIN purchase_order_item poi ON bi.po_item_id = poi.id
                WHERE bi.bpl_id = %s
                ORDER BY poi.fish_name, poi.cut_name, bi.box_number
            """, (bpl_id,))
            box_rows = [dict(r) for r in cur.fetchall()]

            # 4) Fetch pieces for each box
            for box in box_rows:
                cur.execute("""
                    SELECT piece_number, weight_kg
                    FROM box_packaging_list_piece
                    WHERE bpl_item_id = %s
                    ORDER BY piece_number
                """, (box['bpl_item_id'],))
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
                    "pieces": [
                        {"piece_number": p['piece_number'], "weight_kg": float(p['weight_kg'])}
                        for p in box['pieces']
                    ],
                })

            items_list = list(items_map.values())
            total_boxes = sum(len(item['boxes']) for item in items_list)

            # 6) Build email payload
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

            logger.info(f"📧 Sending BPL email for PO {po_row['po_number']} port {port_code}")
            logger.info(f"   Vendor: {po_row['vendor_name']} ({po_row['vendor_email']})")
            logger.info(f"   Items: {len(items_list)}, Email service: {settings.email_service_url}")

        # 7) Call email service (outside the DB cursor context)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.email_service_url}/email/bpl/send-emails",
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
                conn2 = get_connection()
                try:
                    with conn2.cursor(cursor_factory=RealDictCursor) as cur2:
                        cur2.execute("""
                            UPDATE box_packaging_list
                            SET status = 'sent', updated_at = NOW()
                            WHERE po_id = %s AND port_code = %s
                        """, (po_id, port_code))
                        logger.info(f"Updated BPL status to 'sent' for PO {po_id} port {port_code}")

                        # Auto-fulfill: if all accepted ports now have a sent/completed BPL → fulfill
                        cur2.execute(
                            "SELECT COUNT(*) AS cnt FROM purchase_order_port_acceptance WHERE po_id = %s AND status = 'accepted'",
                            (po_id,)
                        )
                        accepted_count = cur2.fetchone()['cnt']

                        cur2.execute("""
                            SELECT COUNT(*) AS cnt
                            FROM box_packaging_list b
                            JOIN purchase_order_port_acceptance p
                              ON b.po_id = p.po_id AND b.port_code = p.port_code
                            WHERE b.po_id = %s AND b.status IN ('sent', 'completed') AND p.status = 'accepted'
                        """, (po_id,))
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
                finally:
                    release_connection(conn2)

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
    finally:
        release_connection(conn)


# ─── PO Status Workflow ──────────────────────────────────────


@router.post("/purchase-orders/{po_id}/accept")
def accept_purchase_order(po_id: int, request: POStatusTransitionRequest):
    """Vendor accepts a purchase order. Only allowed from 'sent' status."""
    conn = get_connection()
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
    finally:
        release_connection(conn)


@router.post("/purchase-orders/{po_id}/reject")
def reject_purchase_order(po_id: int, request: POStatusTransitionRequest):
    """Vendor rejects a purchase order. Only allowed from 'sent' status."""
    conn = get_connection()
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
    finally:
        release_connection(conn)


def _get_port_lists(cur, po_id: int) -> tuple:
    """Return (accepted_ports, rejected_ports) for a PO."""
    cur.execute(
        "SELECT port_code, status FROM purchase_order_port_acceptance WHERE po_id = %s ORDER BY port_code",
        (po_id,)
    )
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
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, status FROM purchase_order WHERE id = %s FOR UPDATE", (po_id,)
            )
            po = cur.fetchone()
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            if po['status'] in ('rejected', 'cancelled'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot accept port on a '{po['status']}' PO"
                )

            # Upsert port with status = 'accepted'
            cur.execute("""
                INSERT INTO purchase_order_port_acceptance
                    (po_id, port_code, status, actor_name, actor_code, notes)
                VALUES (%s, %s, 'accepted', %s, %s, %s)
                ON CONFLICT (po_id, port_code)
                DO UPDATE SET status = 'accepted', actor_name = EXCLUDED.actor_name,
                              actor_code = EXCLUDED.actor_code
            """, (po_id, port_code, request.actor_name, request.actor_code, request.notes))

            # Transition PO status based on current state
            if po['status'] == 'sent':
                # First acceptance — move to accepted
                cur.execute(
                    "UPDATE purchase_order SET status = 'accepted', updated_at = NOW() WHERE id = %s",
                    (po_id,)
                )
                cur.execute("""
                    INSERT INTO purchase_order_audit
                        (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
                    VALUES (%s, 'sent', 'accepted', 'vendor', %s, %s, %s)
                """, (po_id, request.actor_name, request.actor_code, f"Port {port_code} accepted"))
            elif po['status'] == 'fulfilled':
                # New port accepted after fulfill — revert to accepted (new port has no BPL yet)
                cur.execute(
                    "UPDATE purchase_order SET status = 'accepted', updated_at = NOW() WHERE id = %s",
                    (po_id,)
                )
                cur.execute("""
                    INSERT INTO purchase_order_audit
                        (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
                    VALUES (%s, 'fulfilled', 'accepted', 'vendor', %s, %s, %s)
                """, (po_id, request.actor_name, request.actor_code,
                      f"Port {port_code} accepted — awaiting BPL"))

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
    finally:
        release_connection(conn)


@router.post("/purchase-orders/{po_id}/ports/{port_code}/reject")
def reject_port(po_id: int, port_code: str, request: PortAcceptRequest):
    """
    Vendor rejects a specific port. Toggleable — can flip an accepted port to rejected.
    If no accepted ports remain and PO is 'accepted', reverts PO back to 'sent'.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, status FROM purchase_order WHERE id = %s FOR UPDATE", (po_id,)
            )
            po = cur.fetchone()
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            if po['status'] in ('rejected', 'cancelled', 'fulfilled'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change port status on a '{po['status']}' PO"
                )

            # Upsert port with status = 'rejected'
            cur.execute("""
                INSERT INTO purchase_order_port_acceptance
                    (po_id, port_code, status, actor_name, actor_code, notes)
                VALUES (%s, %s, 'rejected', %s, %s, %s)
                ON CONFLICT (po_id, port_code)
                DO UPDATE SET status = 'rejected', actor_name = EXCLUDED.actor_name,
                              actor_code = EXCLUDED.actor_code
            """, (po_id, port_code, request.actor_name, request.actor_code, request.notes))

            # If PO is 'accepted', check remaining accepted ports
            if po['status'] == 'accepted':
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM purchase_order_port_acceptance WHERE po_id = %s AND status = 'accepted'",
                    (po_id,)
                )
                remaining = cur.fetchone()['cnt']
                if remaining == 0:
                    # No accepted ports left — revert to 'sent'
                    cur.execute(
                        "UPDATE purchase_order SET status = 'sent', updated_at = NOW() WHERE id = %s",
                        (po_id,)
                    )
                    cur.execute("""
                        INSERT INTO purchase_order_audit
                            (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
                        VALUES (%s, 'accepted', 'sent', 'vendor', %s, %s, %s)
                    """, (po_id, request.actor_name, request.actor_code,
                          "All ports rejected — PO reverted to received"))
                else:
                    # Check if all remaining accepted ports already have sent/completed BPLs
                    cur.execute("""
                        SELECT COUNT(*) AS cnt
                        FROM purchase_order_port_acceptance p
                        JOIN box_packaging_list b ON p.po_id = b.po_id AND p.port_code = b.port_code
                        WHERE p.po_id = %s AND p.status = 'accepted' AND b.status IN ('sent', 'completed')
                    """, (po_id,))
                    sent_count = cur.fetchone()['cnt']
                    if sent_count >= remaining:
                        # All remaining accepted ports have sent BPLs → re-fulfill
                        cur.execute(
                            "UPDATE purchase_order SET status = 'fulfilled', updated_at = NOW() WHERE id = %s",
                            (po_id,)
                        )
                        cur.execute("""
                            INSERT INTO purchase_order_audit
                                (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
                            VALUES (%s, 'accepted', 'fulfilled', 'system', 'system', 'auto', %s)
                        """, (po_id, f"Port {port_code} rejected — all remaining accepted ports already sent"))

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
    finally:
        release_connection(conn)


@router.get("/purchase-orders/{po_id}/audit")
def get_po_audit(po_id: int):
    """Get the audit trail for a purchase order."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM purchase_order WHERE id = %s", (po_id,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Purchase order not found")

            cur.execute("""
                SELECT id, po_id, from_status, to_status, actor_role,
                       actor_name, actor_code, notes, created_at
                FROM purchase_order_audit
                WHERE po_id = %s
                ORDER BY created_at ASC
            """, (po_id,))
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
    finally:
        release_connection(conn)
