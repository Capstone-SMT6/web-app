from database import engine
from sqlalchemy import text


def main() -> None:
    enum_names = ["goalenum", "genderenum", "skilllevelenum", "intensityenum"]
    with engine.connect() as conn:
        for enum_name in enum_names:
            values = conn.execute(
                text(
                    """
                    SELECT enumlabel
                    FROM pg_enum
                    WHERE enumtypid = (:enum_name)::regtype
                    ORDER BY enumsortorder
                    """
                ),
                {"enum_name": enum_name},
            ).scalars().all()
            print(f"{enum_name}: {', '.join(values)}")


if __name__ == "__main__":
    main()
