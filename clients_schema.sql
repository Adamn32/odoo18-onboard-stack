-- clients_schema.sql
-- Author: Adam ChapChap Ng'uni -- Created: 2025-08-09
CREATE TABLE IF NOT EXISTS clients (id SERIAL PRIMARY KEY, company_name VARCHAR(255) NOT NULL, admin_email VARCHAR(255) NOT NULL, odoo_edition VARCHAR(50) NOT NULL);
