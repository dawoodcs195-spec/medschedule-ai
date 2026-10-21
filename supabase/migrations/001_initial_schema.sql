-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Academic Programs (MBBS, BDS, etc.)
CREATE TABLE IF NOT EXISTS academic_programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(20) NOT NULL UNIQUE, -- e.g., 'MBBS', 'BDS'
    title VARCHAR(250) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Modules / Blocks
CREATE TABLE IF NOT EXISTS modules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    program_id UUID NOT NULL REFERENCES academic_programs(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL, -- e.g., 'BLOCK-IV-MOD-07'
    title VARCHAR(250) NOT NULL, -- e.g., 'Neurosciences Block-IV'
    academic_year INT NOT NULL, -- e.g., 2 for 2nd Year MBBS
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Clinical Departments (Pre-seeded & extensible)
CREATE TABLE IF NOT EXISTS clinical_departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(150) NOT NULL UNIQUE,
    code VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Rooms & Physical Facilities
CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    room_type VARCHAR(50) NOT NULL, -- 'LECTURE_HALL', 'LAB', 'SKILL_LAB', 'SGD_ROOM', 'DIGITAL_LIBRARY'
    capacity INT NOT NULL DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Curriculum Topics & Learning Objectives (Vector Enabled)
CREATE TABLE IF NOT EXISTS learning_objectives (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
    topic_title VARCHAR(250) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    discipline VARCHAR(100) NOT NULL DEFAULT 'General', -- 'Anatomy', 'Physiology', 'Biochemistry', 'Surgery', 'Medicine', etc.
    session_type VARCHAR(50) NOT NULL, -- 'LGIS', 'PRACTICAL', 'SGD', 'DSL', 'SDL', 'PAL', 'MMT'
    organ_system VARCHAR(100), -- 'Neurosciences', 'Cardiovascular', 'Head & Neck', etc.
    faculty_name VARCHAR(150), -- e.g., 'Dr. Ambar Saba', 'CLINICAL FACULTY SURGERY'
    duration_minutes INT NOT NULL DEFAULT 60,
    embedding vector(1536), -- Semantic vector representation for horizontal/vertical integration
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for HNSW Cosine Similarity Search
CREATE INDEX IF NOT EXISTS idx_learning_objectives_embedding_hnsw 
ON learning_objectives 
USING hnsw (embedding vector_cosine_ops);

-- 6. Vertical & Horizontal Curriculum Integrations
CREATE TABLE IF NOT EXISTS curriculum_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_objective_id UUID NOT NULL REFERENCES learning_objectives(id) ON DELETE CASCADE,
    target_objective_id UUID NOT NULL REFERENCES learning_objectives(id) ON DELETE CASCADE,
    integration_type VARCHAR(20) NOT NULL, -- 'HORIZONTAL', 'VERTICAL'
    similarity_score FLOAT NOT NULL,
    is_approved BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_different_objectives CHECK (source_objective_id <> target_objective_id)
);

-- 7. Schedule Slots (Timetable Master Matrix)
CREATE TABLE IF NOT EXISTS schedule_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    objective_id UUID NOT NULL REFERENCES learning_objectives(id) ON DELETE CASCADE,
    room_id UUID REFERENCES rooms(id) ON DELETE SET NULL,
    week_number INT NOT NULL DEFAULT 1,
    day_of_week INT NOT NULL, -- 1 = Monday ... 6 = Saturday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    student_batch_mask VARCHAR(20) NOT NULL DEFAULT 'ALL', -- 'ALL', 'BATCH_A', 'BATCH_B', 'BATCH_C', 'BATCH_D'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Pre-seed Clinical Departments
INSERT INTO clinical_departments (name, code) VALUES
    ('CLINICAL FACULTY SURGERY', 'SURG'),
    ('CLINICAL FACULTY MEDICINE', 'MED'),
    ('CLINICAL FACULTY ENT', 'ENT'),
    ('CLINICAL FACULTY EYE', 'EYE'),
    ('CLINICAL FACULTY PEADS', 'PEAD'),
    ('CLINICAL FACULTY RADIOLOGY', 'RAD'),
    ('ORAL & MAXILLOFACIAL SURGERY', 'OMFS'),
    ('COMMUNITY MEDICINE', 'COMM_MED'),
    ('PATHOLOGY', 'PATH'),
    ('PHARMACOLOGY', 'PHARM')
ON CONFLICT (name) DO NOTHING;

-- 9. Pre-seed Standard Facilities (8 Lecture Halls, 3 Science Labs + 1 Skill Lab, Digital Library)
INSERT INTO rooms (name, room_type, capacity) VALUES
    ('Lecture Hall 1', 'LECTURE_HALL', 100),
    ('Lecture Hall 2', 'LECTURE_HALL', 100),
    ('Lecture Hall 3', 'LECTURE_HALL', 100),
    ('Lecture Hall 4', 'LECTURE_HALL', 100),
    ('Lecture Hall 5', 'LECTURE_HALL', 100),
    ('Lecture Hall 6', 'LECTURE_HALL', 100),
    ('Lecture Hall 7', 'LECTURE_HALL', 100),
    ('Lecture Hall 8', 'LECTURE_HALL', 100),
    ('Histology Lab', 'LAB', 30),
    ('Physiology Lab', 'LAB', 30),
    ('Biochemistry Lab', 'LAB', 30),
    ('Skill Lab', 'SKILL_LAB', 30),
    ('Digital Library / SDL', 'DIGITAL_LIBRARY', 50)
ON CONFLICT (name) DO NOTHING;

-- 10. Pre-seed Sample Academic Program (MBBS & BDS)
INSERT INTO academic_programs (code, title) VALUES
    ('MBBS', 'Bachelor of Medicine, Bachelor of Surgery'),
    ('BDS', 'Bachelor of Dental Surgery')
ON CONFLICT (code) DO NOTHING;
