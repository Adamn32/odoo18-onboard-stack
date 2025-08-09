from celery import Celery
        from .odoo_provision import provision_odoo_company

        app = Celery("tasks", broker="redis://redis:6379/0")

        @app.task
        def create_odoo_company(data):
            result = provision_odoo_company(
                host="odoo_enterprise",
                port=8069,
                db="Savanna",
                user="admin",
                password="admin",
                company_name=data["company_name"],
                modules=data["modules"]
            )
            print(f"Provisioned: {result}")