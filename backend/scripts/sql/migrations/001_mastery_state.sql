create table if not exists mastery_state (
  student_id text not null,
  skill_tag text not null,
  streak integer not null default 0,
  total_attempts integer not null default 0,
  correct_attempts integer not null default 0,
  last_error_type text null,
  mastery_level text not null default 'unknown',
  updated_at timestamptz not null default now(),
  primary key (student_id, skill_tag)
);
