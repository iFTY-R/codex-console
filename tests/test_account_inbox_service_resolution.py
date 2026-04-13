from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.constants import EmailServiceType
from src.database.models import Base, EmailService
from src.web.routes import accounts as accounts_routes


def _create_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session


def test_build_inbox_config_prefers_bound_manual_login_service():
    engine, db = _create_test_db()
    try:
        db.add_all(
            [
                EmailService(
                    service_type="temp_mail",
                    name="fallback-service",
                    enabled=True,
                    priority=0,
                    config={"base_url": "https://wrong.example"},
                ),
                EmailService(
                    service_type="temp_mail",
                    name="bound-service",
                    enabled=True,
                    priority=50,
                    config={"base_url": "https://right.example"},
                ),
            ]
        )
        db.commit()

        bound_service = (
            db.query(EmailService)
            .filter(EmailService.name == "bound-service")
            .first()
        )
        account = SimpleNamespace(
            email="user@right.example",
            extra_data={"manual_login": {"service_db_id": bound_service.id}},
        )

        config = accounts_routes._build_inbox_config(db, EmailServiceType.TEMP_MAIL, account)

        assert config["base_url"] == "https://right.example"
    finally:
        db.close()
        engine.dispose()


def test_build_inbox_config_matches_email_domain_before_priority_fallback():
    engine, db = _create_test_db()
    try:
        db.add_all(
            [
                EmailService(
                    service_type="temp_mail",
                    name="fallback-service",
                    enabled=True,
                    priority=0,
                    config={"base_url": "https://wrong.example", "default_domain": "wrong.example"},
                ),
                EmailService(
                    service_type="temp_mail",
                    name="domain-matched-service",
                    enabled=True,
                    priority=10,
                    config={"api_url": "https://right.example", "domain": "right.example"},
                ),
            ]
        )
        db.commit()

        account = SimpleNamespace(email="user@right.example", extra_data={})

        config = accounts_routes._build_inbox_config(db, EmailServiceType.TEMP_MAIL, account)

        assert config["base_url"] == "https://right.example"
    finally:
        db.close()
        engine.dispose()
