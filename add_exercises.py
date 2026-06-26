from sqlmodel import Session, select
from database import engine
from models import Exercise, ExerciseCategory, ExerciseDifficulty
import uuid

def add_exercises():
    new_exercises = [
        {
            "name": "Squat",
            "slug": "squat",
            "description": "Turun sampai paha sejajar lantai, lutut tidak melewati jari kaki.",
            "category": ExerciseCategory.strength,
            "muscleGroups": ["kaki", "bokong", "paha depan", "legs", "glutes"],
            "difficulty": ExerciseDifficulty.beginner,
            "instructions": ["Berdiri tegak", "Turunkan pinggul", "Kembali ke posisi awal"],
            "isActive": True
        },
        {
            "name": "Plank",
            "slug": "plank",
            "description": "Tahan posisi tubuh lurus selama waktu yang ditentukan.",
            "category": ExerciseCategory.strength,
            "muscleGroups": ["inti", "perut", "punggung bawah", "core", "abs"],
            "difficulty": ExerciseDifficulty.beginner,
            "instructions": ["Posisi tengkurap", "Angkat badan dengan siku", "Tahan posisi lurus"],
            "isActive": True
        },
        {
            "name": "Jumping Jack",
            "slug": "jumping-jack",
            "description": "Lompat sambil membuka kaki dan ayunkan tangan ke atas kepala.",
            "category": ExerciseCategory.cardio,
            "muscleGroups": ["seluruh tubuh", "kardio", "full body", "cardio"],
            "difficulty": ExerciseDifficulty.beginner,
            "instructions": ["Berdiri tegak", "Lompat dan buka kaki", "Kembali ke posisi awal"],
            "isActive": True
        },
        {
            "name": "High Knee",
            "slug": "high-knee",
            "description": "Lari di tempat dengan mengangkat lutut setinggi pinggang.",
            "category": ExerciseCategory.cardio,
            "muscleGroups": ["inti", "kardio", "core", "cardio"],
            "difficulty": ExerciseDifficulty.beginner,
            "instructions": ["Lari di tempat", "Angkat lutut tinggi", "Lakukan dengan cepat"],
            "isActive": True
        },
        {
            "name": "Shoulder Press",
            "slug": "shoulder-press",
            "description": "Angkat beban lurus ke atas kepala, lalu turunkan perlahan.",
            "category": ExerciseCategory.strength,
            "muscleGroups": ["bahu", "triceps", "shoulders"],
            "difficulty": ExerciseDifficulty.beginner,
            "instructions": ["Pegang beban", "Angkat lurus ke atas", "Turunkan perlahan"],
            "isActive": True
        }
    ]

    with Session(engine) as session:
        for ex_data in new_exercises:
            existing = session.exec(select(Exercise).where(Exercise.slug == ex_data["slug"])).first()
            if not existing:
                ex = Exercise(**ex_data)
                session.add(ex)
                print(f"Added {ex.name}")
            else:
                print(f"Already exists {ex.name}")
        session.commit()
        print("Done!")

if __name__ == '__main__':
    add_exercises()
