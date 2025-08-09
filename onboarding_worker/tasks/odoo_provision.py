import odoorpc

def provision_odoo_company(host, port, db, user, password, company_name, modules):
    odoo = odoorpc.ODOO(host, port=port)
    odoo.login(db, user, password)

    Company = odoo.env['res.company']
    new_company = Company.create({'name': company_name})
    print(f"Created company: {company_name} with ID {new_company}")

    Module = odoo.env['ir.module.module']
    for module in modules:
        ids = Module.search([('name', '=', module), ('state', '=', 'uninstalled')])
        if ids:
            Module.button_install(ids)
            print(f"Installing module: {module}")
        else:
            print(f"Module {module} not found or already installed.")
    return {"company_id": new_company, "modules": modules}
