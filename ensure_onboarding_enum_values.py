from database import engine
from sqlalchemy import text


ENUM_VALUES = {
    "goalenum": [
        "menurunkan_berat_badan",
        "menaikkan_berat_badan",
        "menjaga_kebugaran",
        "membentuk_otot",
    ],
    "genderenum": ["pria", "wanita"],
    "skilllevelenum": ["pemula", "menengah", "ahli"],
    "intensityenum": ["rendah", "sedang", "tinggi"],
}


def main() -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for enum_name, values in ENUM_VALUES.items():
            for value in values:
                conn.execute(
                    text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")
                )
    print("Onboarding enum values ensured.")


if __name__ == "__main__":
    main()
