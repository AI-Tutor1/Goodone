"""Factories for student / tutor identity rows in ``master.*``.

These produce plain dicts shaped like the rows the migration creates;
tests that need to insert into the DB (integration tier) use them as
parameter bags for raw SQL ``INSERT``s. The unit tier just needs the
shape — no DB connection required.
"""

from __future__ import annotations

import factory


class StudentFactory(factory.DictFactory):
    """A row in ``master.students``."""

    display_id = factory.Sequence(lambda n: f"S-{n:04d}")
    full_name = factory.Faker("name")
    email = factory.LazyAttribute(
        lambda o: f"{o.full_name.lower().replace(' ', '.')}@example.com",
    )
    country = "AE"
    enrolled_at = factory.Faker("date_this_year")
    status = "active"


class TutorFactory(factory.DictFactory):
    """A row in ``master.tutors``."""

    display_id = factory.Sequence(lambda n: f"T-{n:04d}")
    full_name = factory.Faker("name")
    email = factory.LazyAttribute(
        lambda o: f"{o.full_name.lower().replace(' ', '.')}@example.com",
    )
    country = "PK"
    payment_currency = "PKR"
    hired_at = factory.Faker("date_this_year")
    status = "active"
