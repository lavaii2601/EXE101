-- Saved course/grade rows backing the Student-mode GPA calculator's
-- Premium tier (entitlements.STUDENT_*_LIMITS['gpa_persist']). Free Student
-- users still get a GPA number, just computed from values in the request
-- each time (models/course.py::calculate_gpa) and never written here.
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    term TEXT,
    name TEXT NOT NULL,
    credits DOUBLE PRECISION NOT NULL,
    grade DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_courses_user ON courses (user_id);
