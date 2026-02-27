create table if not exists correction_corpus (
  id              uuid default gen_random_uuid() primary key,
  created_at      timestamptz default now(),
  user_id         uuid,
  topic           text not null,
  subject         text not null,
  grade           text not null,
  question_id     text not null,
  question_text   text not null,
  correction_type text not null,
  before_value    text,
  after_value     text,
  skill_tag       text,
  difficulty      text
);

create index if not exists idx_cc_topic on correction_corpus (topic);
create index if not exists idx_cc_type on correction_corpus (correction_type);
create index if not exists idx_cc_created on correction_corpus (created_at);
