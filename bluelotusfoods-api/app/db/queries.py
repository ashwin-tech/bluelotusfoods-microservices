"""
Database queries for the BlueLotusFoods API
Centralized location for all SQL queries to maintain consistency and readability
Generic query system serving all modules: vendors, dictionary, fish, quotes, email
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
    INSERT INTO quote_product (quote_id, fish_id, weight_range, cut, grade, price_per_kg, quantity)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

# Quote retrieval for email functionality
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

# Debug query for quote details with vendor info
DEBUG_QUOTE_WITH_VENDOR = """
    SELECT 
        q.*,
        v.name as vendor_name,
        v.contact_email,
        v.country as vendor_country
    FROM quote q
    LEFT JOIN vendors v ON q.vendor_id = v.id
    WHERE q.id = %s
"""

# Quote destination queries
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

# Quote product queries
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
# GENERIC QUERY MANAGER CLASS
# =====================================================
class DatabaseQueries:
    """
    Generic database query manager for all BlueLotusFoods API modules
    Provides organized access to all SQL queries across the application
    """
    
    # Schema validation queries
    SCHEMA = {
        'check_email_log': CHECK_EMAIL_LOG_TABLE
    }
    
    # Vendor-related queries
    VENDORS = {
        'get_by_code': GET_VENDOR_BY_CODE,
        'get_by_name': GET_VENDOR_BY_NAME
    }
    
    # Dictionary-related queries
    DICTIONARY = {
        'get_by_category': GET_DICTIONARY_BY_CATEGORY,
        'get_by_code': GET_DICTIONARY_BY_CODE
    }
    
    # Fish-related queries
    FISH = {
        'get_types': GET_FISH_TYPES,
        'get_cuts': GET_FISH_CUTS,
        'get_grades': GET_FISH_GRADES,
        'get_by_name': GET_FISH_BY_NAME,
        'get_cut_by_name': GET_CUT_BY_NAME,
        'get_grade_by_name': GET_GRADE_BY_NAME
    }
    
    # Quote-related queries
    QUOTES = {
        'insert': INSERT_QUOTE,
        'insert_destination': INSERT_QUOTE_DESTINATION,
        'insert_product': INSERT_QUOTE_PRODUCT,
        'get_destinations': GET_QUOTE_DESTINATIONS,
        'get_products': GET_QUOTE_PRODUCTS,
        'debug_with_vendor': DEBUG_QUOTE_WITH_VENDOR
    }
    
    # Email-related queries
    EMAIL = {
        'insert_log': INSERT_EMAIL_LOG,
        'get_vendor_quote': GET_VENDOR_QUOTE_FOR_EMAIL
    }
    

    
    @classmethod
    def get_all_queries(cls):
        """Get all query categories for debugging or documentation"""
        return {
            'schema': cls.SCHEMA,
            'vendors': cls.VENDORS,
            'dictionary': cls.DICTIONARY,
            'fish': cls.FISH,
            'quotes': cls.QUOTES,
            'email': cls.EMAIL
        }


# =====================================================
# USAGE EXAMPLES AND DOCUMENTATION
# =====================================================
"""
Usage Examples:

# Vendor queries
vendor_query = DatabaseQueries.VENDORS['get_by_code']
cur.execute(vendor_query, (vendor_code,))

# Fish queries  
fish_types_query = DatabaseQueries.FISH['get_types']
cur.execute(fish_types_query)

# Quote queries
insert_quote_query = DatabaseQueries.QUOTES['insert']
cur.execute(insert_quote_query, (id, vendor_id, valid_till, notes, negotiable, exclusive))

# Email queries
email_quote_query = DatabaseQueries.EMAIL['get_vendor_quote']  
cur.execute(email_quote_query, (quote_id,))

# Schema validation
check_email_log = DatabaseQueries.SCHEMA['check_email_log']
cur.execute(check_email_log)
"""