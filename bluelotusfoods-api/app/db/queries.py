"""
Database queries for the BlueLotusFoods API
Centralized location for all SQL queries to maintain consistency and readability
"""

# =====================================================
# SCHEMA VALIDATION QUERIES
# =====================================================
CHECK_EMAIL_LOG_TABLE = """
    SELECT table_name FROM information_schema.tables
    WHERE table_name = 'email_log'
"""

# =====================================================
# VENDOR QUERIES
# =====================================================
GET_VENDOR_BY_CODE = """
    SELECT
        v.id,
        v.code,
        v.name,
        v.country,
        COALESCE((SELECT MAX(id) + 1 FROM quote), 1) AS nextQuoteId
    FROM
        vendors v
    WHERE
        v.code = %s
        AND v.active = TRUE
"""

GET_VENDOR_BY_NAME = """
    SELECT id FROM vendors WHERE name = %s AND active = TRUE
"""

GET_VENDOR_CODE = """
    SELECT code FROM vendors WHERE id = %s
"""

# =====================================================
# DICTIONARY QUERIES
# =====================================================
GET_DICTIONARY_BY_CATEGORY = """
    SELECT id, code, name, description
    FROM dictionary
    WHERE category = %s AND active = TRUE
    ORDER BY name
"""

GET_DICTIONARY_BY_CODE = """
    SELECT id FROM dictionary
    WHERE category = 'DESTINATION' AND code = %s AND active = TRUE
"""

# =====================================================
# FISH QUERIES
# =====================================================
GET_FISH_TYPES = """
    SELECT common_name, scientific_name
    FROM fish_species
    WHERE is_active = TRUE
    ORDER BY id
"""

GET_FISH_CUTS = """
    SELECT name FROM fish_cut ORDER BY name
"""

GET_FISH_GRADES = """
    SELECT name FROM fish_grade ORDER BY name
"""

GET_FISH_BY_NAME = """
    SELECT id FROM fish_species
    WHERE common_name = %s AND is_active = TRUE
"""

GET_CUT_BY_NAME = """
    SELECT id FROM fish_cut WHERE name = %s
"""

GET_GRADE_BY_NAME = """
    SELECT id FROM fish_grade WHERE name = %s
"""

# =====================================================
# QUOTE QUERIES
# =====================================================
INSERT_QUOTE = """
    INSERT INTO quote (id, vendor_id, quote_valid_till, notes, price_negotiable, exclusive_offer)
    VALUES (%s, %s, %s, %s, %s, %s)
"""

INSERT_QUOTE_DESTINATION = """
    INSERT INTO quote_destination (quote_id, destination_id, airfreight_per_kg, arrival_date, min_weight, max_weight)
    VALUES (%s, %s, %s, %s, %s, %s)
"""

INSERT_QUOTE_PRODUCT = """
    INSERT INTO quote_product (quote_id, fish_id, weight_range, fish_size_id, cut, grade, price_per_kg, quantity)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

GET_VENDOR_QUOTE_FOR_EMAIL = """
    SELECT
        q.id as quote_id,
        v.name as vendor_name,
        v.country as country_of_origin,
        q.quote_valid_till,
        COALESCE(
            (SELECT string_agg(DISTINCT fs.common_name, ', ')
             FROM quote_product qp
             JOIN fish_species fs ON qp.fish_id = fs.id
             WHERE qp.quote_id = q.id), 'N/A'
        ) as fish_type,
        q.notes,
        q.price_negotiable,
        q.exclusive_offer,
        q.created_at,
        v.code as vendor_code,
        v.contact_email,
        v.is_email_enabled
    FROM quote q
    LEFT JOIN vendors v ON q.vendor_id = v.id
    WHERE q.id = %s
"""

GET_QUOTE_DESTINATIONS = """
    SELECT
        d.name as destination,
        qd.airfreight_per_kg,
        qd.arrival_date,
        qd.min_weight,
        qd.max_weight
    FROM quote_destination qd
    JOIN dictionary d ON qd.destination_id = d.id
    WHERE qd.quote_id = %s
"""

GET_QUOTE_PRODUCTS = """
    SELECT
        fs.common_name as fish_type,
        fc.name as cut_name,
        fg.name as grade_name,
        qp.weight_range,
        qp.price_per_kg,
        qp.quantity
    FROM quote_product qp
    JOIN fish_species fs ON qp.fish_id = fs.id
    JOIN fish_cut fc ON qp.cut = fc.id
    JOIN fish_grade fg ON qp.grade = fg.id
    WHERE qp.quote_id = %s
"""

# =====================================================
# EMAIL AND LOGGING QUERIES
# =====================================================
INSERT_EMAIL_LOG = """
    INSERT INTO email_log (quote_id, vendor_email, status, sent_at)
    VALUES (%s, %s, %s, NOW())
"""

# =====================================================
# ESTIMATES QUERIES  (buyer_pricing/estimates.py)
# =====================================================

# Base query — dynamic vendor/port/date filters and ORDER BY are appended in code
SEARCH_ESTIMATES_BASE = """
    SELECT
        q.id as quote_id,
        q.created_at::date as quote_date,
        v.id as vendor_id,
        v.name as vendor_name,
        d.code as port,
        f.id as fish_species_id,
        f.common_name,
        f.scientific_name,
        fc.id as cut_id,
        fc.name as cut,
        fg.id as grade_id,
        fg.name as grade,
        CASE
            WHEN fsz.lbs_max IS NOT NULL
                THEN fsz.lbs_label::float8::text || '–' || fsz.lbs_max::float8::text
            WHEN fsz.lbs_label IS NOT NULL
                THEN fsz.lbs_label::float8::text
            ELSE qp.weight_range::text
        END AS fish_size,
        qp.fish_size_id,
        qp.quantity as offer_quantity,
        qp.price_per_kg as fish_price,
        qd.airfreight_per_kg as freight_price,
        COALESCE(t.reciprocal_tariff + t.secondary_tariff, 0)
        + COALESCE(tg.reciprocal_tariff + tg.secondary_tariff, 0) as tariff_percent,
        0 as margin,
        0 as clearing_charges
    FROM quote q
    JOIN vendors v ON q.vendor_id = v.id
    LEFT JOIN tariff t ON v.country = t.country AND t.active = true AND t.country != 'Global'
    LEFT JOIN tariff tg ON tg.country = 'Global' AND tg.active = true
    JOIN quote_destination qd ON q.id = qd.quote_id
    JOIN dictionary d ON qd.destination_id = d.id
    JOIN quote_product qp ON q.id = qp.quote_id
    LEFT JOIN fish_size fsz ON qp.fish_size_id = fsz.id
    JOIN fish_species f ON qp.fish_id = f.id
    JOIN fish_cut fc ON qp.cut = fc.id
    JOIN fish_grade fg ON qp.grade = fg.id
    WHERE 1=1
"""

GET_BUYER_PORTS = """
    SELECT d.code
    FROM buyers b
    JOIN company_ports cp ON b.company_id = cp.company_id
    JOIN dictionary d ON cp.port_id = d.id
    WHERE b.id = %s
"""

# Base query — dynamic date filters and ORDER BY are appended in code
GET_BUYER_ESTIMATES_BY_PORT_BASE = """
    SELECT
        q.id as quote_id,
        q.created_at::date as quote_date,
        d.code as port,
        f.common_name,
        fc.name as cut,
        fg.name as grade,
        qp.weight_range as fish_size,
        qp.price_per_kg as fish_price,
        qd.airfreight_per_kg as freight_price,
        COALESCE(t.reciprocal_tariff + t.secondary_tariff, 0)
        + COALESCE(tg.reciprocal_tariff + tg.secondary_tariff, 0) as tariff_percent,
        0 as margin
    FROM quote q
    JOIN vendors v ON q.vendor_id = v.id
    LEFT JOIN tariff t ON v.country = t.country AND t.active = true AND t.country != 'Global'
    LEFT JOIN tariff tg ON tg.country = 'Global' AND tg.active = true
    JOIN quote_destination qd ON q.id = qd.quote_id
    JOIN dictionary d ON qd.destination_id = d.id
    JOIN quote_product qp ON q.id = qp.quote_id
    JOIN fish_species f ON qp.fish_id = f.id
    JOIN fish_cut fc ON qp.cut = fc.id
    JOIN fish_grade fg ON qp.grade = fg.id
    WHERE d.code = ANY(%s)
"""

# =====================================================
# BUYER ESTIMATE QUERIES  (buyer_pricing/buyer_estimates.py)
# =====================================================
INSERT_BUYER_ESTIMATE = """
    INSERT INTO buyer_estimate (
        estimate_number, company_id, buyer_ids, notes,
        delivery_date_from, delivery_date_to, status
    ) VALUES (
        'PENDING', %s, %s, %s, %s, %s, 'draft'
    )
    RETURNING id, estimate_date, delivery_date_from, delivery_date_to, created_at
"""

UPDATE_ESTIMATE_NUMBER = """
    UPDATE buyer_estimate SET estimate_number = %s WHERE id = %s
"""

INSERT_BUYER_ESTIMATE_ITEM = """
    INSERT INTO buyer_estimate_item (
        buyer_estimate_id, vendor_id, quote_id, port_code,
        fish_species_id, cut_id, grade_id, fish_size, fish_size_id,
        fish_price, freight_price, tariff_percent, tariff_amount,
        margin, price, clearing_charges, offer_quantity, total_price
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
"""

INSERT_BUYER_ESTIMATE_REGION_GROUP = """
    INSERT INTO buyer_estimate_region_group (
        buyer_estimate_id, region_name, port_codes, notes
    ) VALUES (%s, %s, %s, %s)
"""

GET_ESTIMATE_ITEMS = """
    SELECT
        bei.*,
        v.name as vendor_name,
        fs.common_name,
        fs.scientific_name,
        fc.name as cut_name,
        fg.name as grade_name
    FROM buyer_estimate_item bei
    JOIN vendors v ON bei.vendor_id = v.id
    JOIN fish_species fs ON bei.fish_species_id = fs.id
    JOIN fish_cut fc ON bei.cut_id = fc.id
    JOIN fish_grade fg ON bei.grade_id = fg.id
    WHERE bei.buyer_estimate_id = %s
    ORDER BY v.name, fs.common_name
"""

GET_BUYER_ESTIMATES_LIST = """
    SELECT
        be.id,
        be.estimate_number,
        be.buyer_ids,
        be.company_id,
        be.estimate_date,
        be.delivery_date_from,
        be.delivery_date_to,
        be.status,
        be.notes,
        be.created_at,
        be.updated_at,
        c.name as company_name,
        COUNT(bei.id) as item_count,
        (
            SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
            FROM buyers
            WHERE buyers.id IN (
                SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
            )
        ) as buyer_names
    FROM buyer_estimate be
    JOIN company c ON be.company_id = c.id
    LEFT JOIN buyer_estimate_item bei ON be.id = bei.buyer_estimate_id
    WHERE %s = ANY(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
    GROUP BY be.id, c.name
    ORDER BY be.created_at DESC
    LIMIT %s
"""

GET_ESTIMATE_HEADER = """
    SELECT
        be.*,
        c.name as company_name,
        (
            SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
            FROM buyers
            WHERE buyers.id IN (
                SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
            )
        ) as buyer_names,
        (
            SELECT STRING_AGG(buyers.email, ', ' ORDER BY buyers.name)
            FROM buyers
            WHERE buyers.id IN (
                SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
            )
        ) as buyer_emails
    FROM buyer_estimate be
    JOIN company c ON be.company_id = c.id
    WHERE be.id = %s
"""

GET_ESTIMATE_REGION_GROUPS = """
    SELECT * FROM buyer_estimate_region_group
    WHERE buyer_estimate_id = %s
    ORDER BY region_name
"""

UPDATE_ESTIMATE_STATUS = """
    UPDATE buyer_estimate
    SET status = %s
    WHERE id = %s
    RETURNING id, estimate_number, status
"""

UPDATE_ESTIMATE_STATUS_SENT = """
    UPDATE buyer_estimate SET status = 'sent', updated_at = NOW() WHERE id = %s
"""

GET_COMPANY_ESTIMATES = """
    SELECT
        be.id,
        be.estimate_number,
        be.buyer_ids,
        be.company_id,
        be.estimate_date,
        be.delivery_date_from,
        be.delivery_date_to,
        be.status,
        be.notes,
        be.created_at,
        be.updated_at,
        c.name as company_name,
        (
            SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
            FROM buyers
            WHERE buyers.id IN (
                SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
            )
        ) as all_buyers
    FROM buyer_estimate be
    JOIN company c ON be.company_id = c.id
    WHERE be.company_id = %s
      AND be.created_at >= %s::date
      AND be.created_at < %s::date + INTERVAL '7 days'
    ORDER BY be.created_at DESC
"""

GET_COMPANY_ESTIMATE_ITEMS = """
    SELECT
        bei.id,
        bei.buyer_estimate_id,
        bei.vendor_id,
        bei.quote_id,
        v.name as vendor_name,
        bei.port_code,
        bei.fish_species_id,
        fs.common_name,
        fs.scientific_name,
        bei.cut_id,
        fc.name as cut_name,
        bei.grade_id,
        fg.name as grade_name,
        bei.fish_size,
        bei.fish_size_id,
        bei.fish_price,
        bei.freight_price,
        bei.tariff_percent,
        bei.tariff_amount,
        bei.margin,
        bei.price,
        bei.clearing_charges,
        bei.offer_quantity,
        bei.total_price
    FROM buyer_estimate_item bei
    JOIN vendors v ON bei.vendor_id = v.id
    JOIN fish_species fs ON bei.fish_species_id = fs.id
    JOIN fish_cut fc ON bei.cut_id = fc.id
    JOIN fish_grade fg ON bei.grade_id = fg.id
    WHERE bei.buyer_estimate_id = %s
    ORDER BY bei.offer_quantity, v.name, fs.common_name
"""

GET_BUYER_EMAILS_FOR_ESTIMATE = """
    SELECT email
    FROM buyers
    WHERE id IN (
        SELECT UNNEST(STRING_TO_ARRAY(%s, ',')::INTEGER[])
    )
    AND email IS NOT NULL
    AND is_email_enabled = true
"""

GET_VENDOR_QUOTES_HEADER = """
    SELECT
        q.id as quote_id,
        q.vendor_id,
        v.name as vendor_name,
        v.code as vendor_code,
        v.contact_email as vendor_email,
        v.country as country_of_origin,
        q.quote_valid_till,
        q.notes,
        q.price_negotiable,
        q.exclusive_offer,
        q.created_at as quote_date
    FROM quote q
    JOIN vendors v ON q.vendor_id = v.id
    WHERE q.id = ANY(%s)
"""

GET_VENDOR_QUOTE_PRODUCTS = """
    SELECT
        qp.quote_id,
        fs.common_name as fish_type,
        fc.name as cut_name,
        fg.name as grade_name,
        qp.weight_range,
        qp.fish_size_id,
        fsz.lbs_label,
        fsz.lbs_max,
        qp.price_per_kg,
        qp.quantity
    FROM quote_product qp
    JOIN fish_species fs ON qp.fish_id = fs.id
    JOIN fish_cut fc ON qp.cut = fc.id
    JOIN fish_grade fg ON qp.grade = fg.id
    LEFT JOIN fish_size fsz ON qp.fish_size_id = fsz.id
    WHERE qp.quote_id = ANY(%s)
"""

GET_VENDOR_QUOTE_DESTINATIONS = """
    SELECT
        qd.quote_id,
        d.name as destination,
        d.code as destination_code,
        qd.airfreight_per_kg,
        qd.arrival_date,
        qd.min_weight,
        qd.max_weight
    FROM quote_destination qd
    JOIN dictionary d ON qd.destination_id = d.id
    WHERE qd.quote_id = ANY(%s)
"""

# =====================================================
# PURCHASE ORDER QUERIES
# =====================================================
CHECK_PO_EXISTS = """
    SELECT id, po_number, status FROM purchase_order
    WHERE quote_id = %s AND estimate_id = %s AND vendor_id = %s
"""

INSERT_PURCHASE_ORDER = """
    INSERT INTO purchase_order
        (po_number, quote_id, estimate_id, vendor_id, status, delivery_date_from, delivery_date_to)
    VALUES (%s, %s, %s, %s, 'sent', %s, %s)
    RETURNING id, po_number, status, created_at
"""

INSERT_PURCHASE_ORDER_ITEM = """
    INSERT INTO purchase_order_item
        (po_id, fish_name, cut_name, grade_name, fish_size, port_code,
         destination_name, price_per_kg, airfreight_per_kg, total_per_kg,
         order_weight_lbs, order_weight_kg)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

GET_PO_FOR_UPDATE = """
    SELECT id, status FROM purchase_order WHERE id = %s FOR UPDATE
"""

GET_PO_STATUS = """
    SELECT status FROM purchase_order WHERE id = %s
"""

UPDATE_PO_STATUS = """
    UPDATE purchase_order SET status = %s, updated_at = NOW() WHERE id = %s
"""

INSERT_PO_AUDIT = """
    INSERT INTO purchase_order_audit
        (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

GET_POS_BY_ESTIMATE = """
    SELECT
        po.id, po.po_number, po.quote_id, po.estimate_id,
        po.vendor_id, po.status, po.created_at
    FROM purchase_order po
    WHERE po.estimate_id = %s
    ORDER BY po.created_at DESC
"""

GET_PO_ITEMS_SUMMARY = """
    SELECT fish_name, cut_name, grade_name, fish_size,
           port_code, order_weight_lbs, order_weight_kg
    FROM purchase_order_item
    WHERE po_id = %s
    ORDER BY port_code, fish_name
"""

GET_PO_HEADER_WITH_ESTIMATE = """
    SELECT
        po.id, po.po_number, po.quote_id, po.estimate_id,
        po.vendor_id, po.status, po.created_at,
        be.estimate_number
    FROM purchase_order po
    JOIN buyer_estimate be ON po.estimate_id = be.id
    WHERE po.id = %s
"""

GET_PO_ITEMS_FULL = """
    SELECT
        id, fish_name, cut_name, grade_name, fish_size,
        port_code, destination_name, price_per_kg,
        airfreight_per_kg, total_per_kg,
        order_weight_lbs, order_weight_kg
    FROM purchase_order_item
    WHERE po_id = %s
    ORDER BY port_code, fish_name
"""

GET_PORT_ACCEPTANCE = """
    SELECT port_code, status FROM purchase_order_port_acceptance
    WHERE po_id = %s ORDER BY port_code
"""

UPSERT_PORT_ACCEPTANCE = """
    INSERT INTO purchase_order_port_acceptance
        (po_id, port_code, status, actor_name, actor_code, notes)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (po_id, port_code)
    DO UPDATE SET status = EXCLUDED.status,
                  actor_name = EXCLUDED.actor_name,
                  actor_code = EXCLUDED.actor_code
"""

GET_REMAINING_ACCEPTED_PORTS = """
    SELECT COUNT(*) AS cnt FROM purchase_order_port_acceptance
    WHERE po_id = %s AND status = 'accepted'
"""

GET_VENDOR_POS_BY_WEEK = """
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
"""

GET_VENDOR_POS_ALL = """
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
"""

# =====================================================
# BOX PACKAGING LIST (BPL) QUERIES
# =====================================================
GET_BPLS_FOR_PO = """
    SELECT id, po_id, port_code, status, notes,
           invoice_number, air_way_bill, packed_date, expiry_date,
           created_at, updated_at
    FROM box_packaging_list
    WHERE po_id = %s
    ORDER BY port_code
"""

GET_BPL_BOXES = """
    SELECT
        bi.id, bi.po_item_id, bi.box_number, bi.num_pieces,
        bi.net_weight_kg, bi.gross_weight_kg,
        bi.weight_range_from_kg, bi.weight_range_to_kg,
        poi.fish_name, poi.cut_name, poi.grade_name, poi.fish_size
    FROM box_packaging_list_item bi
    JOIN purchase_order_item poi ON bi.po_item_id = poi.id
    WHERE bi.bpl_id = %s
    ORDER BY bi.box_number
"""

GET_BPL_PIECES = """
    SELECT id, piece_number, weight_kg
    FROM box_packaging_list_piece
    WHERE bpl_item_id = %s
    ORDER BY piece_number
"""

GET_COVERED_PO_ITEMS = """
    SELECT DISTINCT bi.po_item_id
    FROM box_packaging_list_item bi
    JOIN box_packaging_list bpl ON bi.bpl_id = bpl.id
    WHERE bpl.po_id = %s
"""

CHECK_PORT_ACCEPTED = """
    SELECT id FROM purchase_order_port_acceptance
    WHERE po_id = %s AND port_code = %s AND status = 'accepted'
"""

GET_BPL_BY_PO_PORT = """
    SELECT id FROM box_packaging_list
    WHERE po_id = %s AND port_code = %s
"""

UPDATE_BPL = """
    UPDATE box_packaging_list
    SET status = %s, notes = %s,
        invoice_number = %s, air_way_bill = %s,
        packed_date = %s, expiry_date = %s,
        updated_at = NOW()
    WHERE id = %s
"""

DELETE_BPL_ITEMS = """
    DELETE FROM box_packaging_list_item WHERE bpl_id = %s
"""

INSERT_BPL = """
    INSERT INTO box_packaging_list
        (po_id, port_code, status, notes,
         invoice_number, air_way_bill, packed_date, expiry_date)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""

INSERT_BPL_ITEM = """
    INSERT INTO box_packaging_list_item
        (bpl_id, po_item_id, box_number, box_count, num_pieces,
         net_weight_kg, gross_weight_kg,
         weight_range_from_kg, weight_range_to_kg)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""

INSERT_BPL_PIECE = """
    INSERT INTO box_packaging_list_piece
        (bpl_item_id, piece_number, weight_kg)
    VALUES (%s, %s, %s)
"""

GET_PO_FOR_BPL_EMAIL = """
    SELECT
        po.id, po.po_number, po.vendor_id,
        v.name AS vendor_name,
        v.contact_email AS vendor_email,
        v.country AS vendor_country
    FROM purchase_order po
    JOIN vendors v ON po.vendor_id = v.id
    WHERE po.id = %s
"""

GET_BPL_HEADER = """
    SELECT id, invoice_number, air_way_bill, packed_date, expiry_date,
           uploaded_file_path, uploaded_file_name
    FROM box_packaging_list
    WHERE po_id = %s AND port_code = %s
"""

GET_BPL_ITEMS_FOR_EMAIL = """
    SELECT
        bi.id AS bpl_item_id, bi.po_item_id, bi.box_number, bi.num_pieces,
        bi.net_weight_kg, bi.weight_range_from_kg, bi.weight_range_to_kg,
        poi.fish_name, poi.cut_name, poi.grade_name, poi.fish_size,
        poi.order_weight_kg
    FROM box_packaging_list_item bi
    JOIN purchase_order_item poi ON bi.po_item_id = poi.id
    WHERE bi.bpl_id = %s
    ORDER BY poi.fish_name, poi.cut_name, bi.box_number
"""

GET_BPL_PIECES_FOR_EMAIL = """
    SELECT piece_number, weight_kg
    FROM box_packaging_list_piece
    WHERE bpl_item_id = %s
    ORDER BY piece_number
"""

UPDATE_BPL_STATUS_SENT = """
    UPDATE box_packaging_list SET status = 'sent', updated_at = NOW()
    WHERE po_id = %s AND port_code = %s
"""

GET_ACCEPTED_PORT_COUNT = """
    SELECT COUNT(*) AS cnt FROM purchase_order_port_acceptance
    WHERE po_id = %s AND status = 'accepted'
"""

GET_SENT_BPL_COUNT = """
    SELECT COUNT(*) AS cnt
    FROM box_packaging_list b
    JOIN purchase_order_port_acceptance p
      ON b.po_id = p.po_id AND b.port_code = p.port_code
    WHERE b.po_id = %s AND b.status = 'sent' AND p.status = 'accepted'
"""

GET_PO_CREATED_AT = """
    SELECT id, created_at FROM purchase_order WHERE id = %s
"""

GET_PO_AUDIT_TIMESTAMPS = """
    SELECT
        MIN(CASE WHEN to_status = 'accepted' THEN created_at END) AS accepted_at,
        MAX(CASE WHEN to_status = 'fulfilled' THEN created_at END) AS fulfilled_at
    FROM purchase_order_audit
    WHERE po_id = %s
"""

GET_PO_AUDIT_RECORDS = """
    SELECT id, po_id, from_status, to_status, actor_role,
           actor_name, actor_code, notes, created_at
    FROM purchase_order_audit
    WHERE po_id = %s
    ORDER BY created_at ASC
"""

# =====================================================
# BUYER PRICING QUERIES
# =====================================================

GET_ALL_BUYERS = """
    SELECT b.id, b.name, b.email, b.company_id, c.name AS company_name, b.active
    FROM buyers b
    JOIN company c ON b.company_id = c.id
    WHERE b.active = TRUE
    ORDER BY c.name, b.name
"""

GET_BUYER_BY_ID = """
    SELECT b.id, b.name, b.email, b.company_id, c.name AS company_name, b.active
    FROM buyers b
    JOIN company c ON b.company_id = c.id
    WHERE b.id = %s
"""

GET_COMPANY_PORTS = """
    SELECT d.id, d.code, d.name
    FROM company_ports cp
    JOIN dictionary d ON cp.port_id = d.id
    WHERE cp.company_id = %s
    ORDER BY d.code
"""

GET_BUYERS_BY_COMPANY = """
    SELECT b.id, b.name, b.email, b.company_id, c.name AS company_name, b.active
    FROM buyers b
    JOIN company c ON b.company_id = c.id
    WHERE b.company_id = %s AND b.active = TRUE
    ORDER BY b.name
"""

GET_ALL_VENDORS_FOR_PRICING = """
    SELECT id, name, code, country, contact_email
    FROM vendors
    WHERE active = TRUE
    ORDER BY name
"""


UPDATE_BPL_UPLOAD = """
    UPDATE box_packaging_list
    SET status = 'completed',
        uploaded_file_path = %s,
        uploaded_file_name = %s,
        invoice_number = %s, air_way_bill = %s,
        packed_date = %s, expiry_date = %s,
        notes = %s, updated_at = NOW()
    WHERE id = %s
"""

INSERT_BPL_UPLOAD = """
    INSERT INTO box_packaging_list
        (po_id, port_code, status, uploaded_file_path, uploaded_file_name,
         invoice_number, air_way_bill, packed_date, expiry_date, notes)
    VALUES (%s, %s, 'completed', %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""


# =====================================================
# QUERY MANAGER CLASS
# =====================================================
class DatabaseQueries:
    """Organized access to all SQL queries across the application."""

    SCHEMA = {
        'check_email_log': CHECK_EMAIL_LOG_TABLE,
    }

    VENDORS = {
        'get_by_code': GET_VENDOR_BY_CODE,
        'get_by_name': GET_VENDOR_BY_NAME,
        'get_code': GET_VENDOR_CODE,
    }

    BUYER_PRICING = {
        'get_all_buyers': GET_ALL_BUYERS,
        'get_buyer_by_id': GET_BUYER_BY_ID,
        'get_company_ports': GET_COMPANY_PORTS,
        'get_buyers_by_company': GET_BUYERS_BY_COMPANY,
        'get_all_vendors': GET_ALL_VENDORS_FOR_PRICING,
    }

    DICTIONARY = {
        'get_by_category': GET_DICTIONARY_BY_CATEGORY,
        'get_by_code': GET_DICTIONARY_BY_CODE,
    }

    FISH = {
        'get_types': GET_FISH_TYPES,
        'get_cuts': GET_FISH_CUTS,
        'get_grades': GET_FISH_GRADES,
        'get_by_name': GET_FISH_BY_NAME,
        'get_cut_by_name': GET_CUT_BY_NAME,
        'get_grade_by_name': GET_GRADE_BY_NAME,
    }

    QUOTES = {
        'insert': INSERT_QUOTE,
        'insert_destination': INSERT_QUOTE_DESTINATION,
        'insert_product': INSERT_QUOTE_PRODUCT,
        'get_destinations': GET_QUOTE_DESTINATIONS,
        'get_products': GET_QUOTE_PRODUCTS,
        'get_for_email': GET_VENDOR_QUOTE_FOR_EMAIL,
        'debug_with_vendor': GET_VENDOR_QUOTE_FOR_EMAIL,
    }

    EMAIL = {
        'insert_log': INSERT_EMAIL_LOG,
        'get_vendor_quote': GET_VENDOR_QUOTE_FOR_EMAIL,
    }

    ESTIMATES = {
        'search_base': SEARCH_ESTIMATES_BASE,
        'buyer_ports': GET_BUYER_PORTS,
        'buyer_estimates_base': GET_BUYER_ESTIMATES_BY_PORT_BASE,
    }

    BUYER_ESTIMATES = {
        'insert_estimate': INSERT_BUYER_ESTIMATE,
        'update_estimate_number': UPDATE_ESTIMATE_NUMBER,
        'insert_item': INSERT_BUYER_ESTIMATE_ITEM,
        'insert_region_group': INSERT_BUYER_ESTIMATE_REGION_GROUP,
        'get_items': GET_ESTIMATE_ITEMS,
        'list_by_buyer': GET_BUYER_ESTIMATES_LIST,
        'get_header': GET_ESTIMATE_HEADER,
        'get_region_groups': GET_ESTIMATE_REGION_GROUPS,
        'update_status': UPDATE_ESTIMATE_STATUS,
        'update_status_sent': UPDATE_ESTIMATE_STATUS_SENT,
        'list_by_company': GET_COMPANY_ESTIMATES,
        'get_company_items': GET_COMPANY_ESTIMATE_ITEMS,
        'get_buyer_emails': GET_BUYER_EMAILS_FOR_ESTIMATE,
        'get_vendor_quotes_header': GET_VENDOR_QUOTES_HEADER,
        'get_vendor_quote_products': GET_VENDOR_QUOTE_PRODUCTS,
        'get_vendor_quote_destinations': GET_VENDOR_QUOTE_DESTINATIONS,
    }

    PURCHASE_ORDERS = {
        'check_exists': CHECK_PO_EXISTS,
        'insert': INSERT_PURCHASE_ORDER,
        'insert_item': INSERT_PURCHASE_ORDER_ITEM,
        'get_for_update': GET_PO_FOR_UPDATE,
        'get_status': GET_PO_STATUS,
        'update_status': UPDATE_PO_STATUS,
        'insert_audit': INSERT_PO_AUDIT,
        'get_by_estimate': GET_POS_BY_ESTIMATE,
        'get_items_summary': GET_PO_ITEMS_SUMMARY,
        'get_header_with_estimate': GET_PO_HEADER_WITH_ESTIMATE,
        'get_items_full': GET_PO_ITEMS_FULL,
        'get_port_acceptance': GET_PORT_ACCEPTANCE,
        'upsert_port_acceptance': UPSERT_PORT_ACCEPTANCE,
        'get_remaining_accepted_ports': GET_REMAINING_ACCEPTED_PORTS,
        'get_vendor_pos_by_week': GET_VENDOR_POS_BY_WEEK,
        'get_vendor_pos_all': GET_VENDOR_POS_ALL,
        'get_created_at': GET_PO_CREATED_AT,
        'get_audit_timestamps': GET_PO_AUDIT_TIMESTAMPS,
        'get_audit_records': GET_PO_AUDIT_RECORDS,
    }

    BPL = {
        'get_for_po': GET_BPLS_FOR_PO,
        'get_boxes': GET_BPL_BOXES,
        'get_pieces': GET_BPL_PIECES,
        'get_covered_items': GET_COVERED_PO_ITEMS,
        'check_port_accepted': CHECK_PORT_ACCEPTED,
        'get_by_po_port': GET_BPL_BY_PO_PORT,
        'update': UPDATE_BPL,
        'delete_items': DELETE_BPL_ITEMS,
        'insert': INSERT_BPL,
        'insert_item': INSERT_BPL_ITEM,
        'insert_piece': INSERT_BPL_PIECE,
        'get_po_for_email': GET_PO_FOR_BPL_EMAIL,
        'get_header': GET_BPL_HEADER,
        'get_items_for_email': GET_BPL_ITEMS_FOR_EMAIL,
        'get_pieces_for_email': GET_BPL_PIECES_FOR_EMAIL,
        'update_status_sent': UPDATE_BPL_STATUS_SENT,
        'get_accepted_port_count': GET_ACCEPTED_PORT_COUNT,
        'get_sent_bpl_count': GET_SENT_BPL_COUNT,
        'update_upload': UPDATE_BPL_UPLOAD,
        'insert_upload': INSERT_BPL_UPLOAD,
    }
