-- Extensions. pgvector provides the halfvec/sparsevec/vector types used by the
-- chunks table and the HNSW index; pg_search (ParadeDB) provides the bm25 index
-- access method. Both must be created before any object that depends on them.
-- pg_search requires the paradedb/paradedb image — the plain pgvector image does
-- not ship it and CREATE EXTENSION will fail there.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

-- DROP SEQUENCE attachments_id_seq;

CREATE SEQUENCE attachments_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE chunking_logging_id_seq;

CREATE SEQUENCE chunking_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE embedding_logging_id_seq;

CREATE SEQUENCE embedding_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE file_counters_id_seq;

CREATE SEQUENCE file_counters_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE step_timings_id_seq;

CREATE SEQUENCE step_timings_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE summaries_logging_id_seq;

CREATE SEQUENCE summaries_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE test_generation_accuracy_logging_id_seq;

CREATE SEQUENCE test_generation_accuracy_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE test_retrieval_chunk_logging_id_seq;

CREATE SEQUENCE test_retrieval_chunk_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE test_retrieval_vk_logging_id_seq;

CREATE SEQUENCE test_retrieval_vk_logging_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;-- public.chunks definition

-- Drop table

-- DROP TABLE chunks;

CREATE TABLE chunks (
	chunk_id uuid DEFAULT gen_random_uuid() NOT NULL,
	source_type text NOT NULL,
	source_id text NOT NULL,
	voyage_key text NOT NULL,
	chunk_index int4 NOT NULL,
	"text" text NOT NULL,
	embedding public.halfvec(2560) NULL,
	char_count int4 NULL,
	strategy text DEFAULT 'paragraph'::text NOT NULL,
	model text NULL,
	thread_id uuid NULL,
	text_tsv tsvector GENERATED ALWAYS AS (
CASE
    WHEN strategy = ANY (ARRAY['context'::text, 'plain'::text, 'late'::text, 'summary'::text]) THEN to_tsvector('simple'::regconfig, text)
    ELSE NULL::tsvector
END) STORED NULL,
	CONSTRAINT chunks_pkey PRIMARY KEY (chunk_id),
	CONSTRAINT chunks_source_type_check CHECK ((source_type = ANY (ARRAY['email_summaries'::text, 'fixture_summaries'::text, 'phase'::text, 'llm_structured'::text, 'email'::text, 'attachment'::text]))),
	CONSTRAINT chunks_source_type_source_id_strategy_chunk_index_key UNIQUE (source_type, source_id, strategy, chunk_index),
	CONSTRAINT chunks_strategy_check CHECK ((strategy = ANY (ARRAY['late'::text, 'context'::text, 'plain'::text, 'summary'::text])))
);
CREATE INDEX chunks_bm25_idx ON public.chunks USING bm25 (chunk_id, text, strategy, voyage_key, source_type) WITH (key_field=chunk_id);
CREATE INDEX chunks_embedding_hnsw_idx ON public.chunks USING hnsw (embedding halfvec_cosine_ops) WITH (m='16', ef_construction='64');
CREATE INDEX chunks_source_idx ON public.chunks USING btree (source_type, source_id);
CREATE INDEX chunks_text_tsv_gin ON public.chunks USING gin (text_tsv) WHERE (strategy = ANY (ARRAY['context'::text, 'plain'::text, 'late'::text, 'summary'::text]));
CREATE INDEX chunks_thread_id_idx ON public.chunks USING btree (thread_id) WHERE (thread_id IS NOT NULL);
CREATE INDEX chunks_voyage_idx ON public.chunks USING btree (voyage_key);


-- public.docling definition

-- Drop table

-- DROP TABLE docling;

CREATE TABLE docling (
	sha256 bpchar(64) NOT NULL,
	markdown text NULL,
	char_count int4 NULL,
	token_count int4 NULL,
	processed_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT docling_pkey PRIMARY KEY (sha256)
);


-- public.emails definition

-- Drop table

-- DROP TABLE emails;

CREATE TABLE emails (
	email_id uuid NOT NULL,
	voyage_key text NOT NULL,
	thread_id uuid NOT NULL,
	eml_path text NOT NULL,
	direction text NOT NULL,
	mailbox text NULL,
	subject text NULL,
	from_addr text NULL,
	to_addr _text NULL,
	sent_at timestamptz NULL,
	body_text text NULL,
	body_html text NULL,
	body_cleaned text NULL,
	has_attachment bool DEFAULT false NOT NULL,
	raw_headers jsonb NULL,
	email_json jsonb NOT NULL,
	CONSTRAINT emails_direction_check CHECK ((direction = ANY (ARRAY['in'::text, 'out'::text]))),
	CONSTRAINT emails_pkey PRIMARY KEY (email_id)
);
CREATE INDEX emails_sent_at_idx ON public.emails USING btree (sent_at);
CREATE INDEX emails_thread_idx ON public.emails USING btree (thread_id);
CREATE INDEX emails_voyage_idx ON public.emails USING btree (voyage_key);


-- public.fixture_summaries definition

-- Drop table

-- DROP TABLE fixture_summaries;

CREATE TABLE fixture_summaries (
	voyage_key text NOT NULL,
	summary text DEFAULT ''::text NOT NULL,
	status text DEFAULT 'ok'::text NOT NULL,
	log text NULL,
	generated_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT fixture_summaries_pkey PRIMARY KEY (voyage_key),
	CONSTRAINT fixture_summaries_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text])))
);


-- public.fixtures definition

-- Drop table

-- DROP TABLE fixtures;

CREATE TABLE fixtures (
	voyage_key text NOT NULL,
	profit_centre text NULL,
	vessel_name text NULL,
	voyage_no int4 NULL,
	voyage_ref int4 NULL,
	voyage_type text NULL,
	voyage_status text NULL,
	fixed_by text NULL,
	operated_by text NULL,
	strategy text NULL,
	allfixtures_year int4 NULL,
	allfixtures_no int4 NULL,
	fixture_owner text NULL,
	fixture_charterer text NULL,
	fixture_contractdate timestamptz NULL,
	fixture_fromrange text NULL,
	fixture_torange text NULL,
	fixture_laycandisp text NULL,
	fixture_laycanfrom timestamptz NULL,
	fixture_laycanto timestamptz NULL,
	commodity text NULL,
	fixture_estquantity numeric NULL,
	fixture_loadedtodate numeric NULL,
	fixture_checked text NULL,
	fixture_ldquantity numeric NULL,
	fixture_ldquantityunit text NULL,
	fixture_cargoagent text NULL,
	fixture_blquantity numeric NULL,
	fixture_blquantityunit text NULL,
	fixture_demurragerate numeric NULL,
	fixture_demurrageratecur text NULL,
	fixture_despatchrate numeric NULL,
	fixture_despatchratecur text NULL,
	fixture_loadrate numeric NULL,
	fixture_loadrateunit text NULL,
	fixture_shincshextype text NULL,
	fixture_nor timestamptz NULL,
	fixture_commenced timestamptz NULL,
	fixture_complete timestamptz NULL,
	fixture_vmheadtype text NULL,
	fixture_bldate timestamptz NULL,
	fixture_loaddischargetype text NULL,
	fixture_liftedfor text NULL,
	fixture_loi text NULL,
	fixture_blrorbla text NULL,
	fixture_ldportname text NULL,
	fixture_ldportarrived timestamptz NULL,
	fixture_ldportsailed timestamptz NULL,
	fixture_descr text NULL,
	fixture_cargoout text NULL,
	fixture_cargoref text NULL,
	fixture_remarkslong text NULL,
	fixture_remarks text NULL,
	allfixtures_broker1 text NULL,
	allfixtures_broker2 text NULL,
	allfixtures_broker3 text NULL,
	allfixtures_broker4 text NULL,
	allfixtures_remarks text NULL,
	allfixtures_fixturetype text NULL,
	allfixtures_deliveredgmt timestamptz NULL,
	allfixtures_redeliveredgmt timestamptz NULL,
	allfixtures_status text NULL,
	allfixtures_spotvoyage text NULL,
	allfixtures_externalfixtureref text NULL,
	allfixtures_contractform text NULL,
	fixture_load_country text NULL,
	username text NULL,
	first_port_date_gmt timestamptz NULL,
	last_port_date_gmt timestamptz NULL,
	product_name text NULL,
	cargo_type text NULL,
	trade_area text NULL,
	size_class text NULL,
	profit_centre_code text NULL,
	cargo_un_number text NULL,
	today_less_one_year timestamptz NULL,
	laycan_performance text NULL,
	laycan_performance_state text NULL,
	vessel_imo int4 NULL,
	market_value numeric NULL,
	market_value_adj numeric NULL,
	cargo_adj_value numeric NULL,
	freight_rate numeric NULL,
	lastdischargeportname text NULL,
	lastdischargeportcountry text NULL,
	voyage_id int4 NULL,
	ofac_restricted text NULL,
	cargo_checked text NULL,
	cargo_checkedby text NULL,
	cargo_checkedat timestamptz NULL,
	hf_id int4 NULL,
	analysis_code text NULL,
	cargo_remarks text NULL,
	voyage_checked1 text NULL,
	voyage_checked2 text NULL,
	voyage_checked3 text NULL,
	voyage_checkedby1 text NULL,
	voyage_checkedby2 text NULL,
	voyage_checkedby3 text NULL,
	voyage_checkedat1 timestamptz NULL,
	voyage_checkedat2 timestamptz NULL,
	voyage_checkedat3 timestamptz NULL,
	fixing_department text NULL,
	operating_department text NULL,
	subtype_display text NULL,
	bl_year int4 NULL,
	loaded_at timestamptz DEFAULT now() NULL,
	CONSTRAINT fixtures_pkey PRIMARY KEY (voyage_key)
);


-- public.ground_truth definition

-- Drop table

-- DROP TABLE ground_truth;

CREATE TABLE ground_truth (
	question_id uuid DEFAULT gen_random_uuid() NOT NULL,
	question text NOT NULL,
	category text NOT NULL,
	answer text NOT NULL,
	body_cleaned text NULL,
	structured_md text NULL,
	thread_id uuid NOT NULL,
	source_id uuid NOT NULL,
	voyage_key text NOT NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	question_reformulated text NULL,
	CONSTRAINT ground_truth_category_check CHECK ((category = ANY (ARRAY['fact_single'::text, 'reasoning'::text, 'summary'::text, 'unanswerable'::text]))),
	CONSTRAINT ground_truth_pkey PRIMARY KEY (question_id),
	CONSTRAINT ground_truth_source_id_category_key UNIQUE (source_id, category)
);
CREATE INDEX gt_category_idx ON public.ground_truth USING btree (category);
CREATE INDEX gt_thread_idx ON public.ground_truth USING btree (thread_id);
CREATE INDEX gt_voyage_idx ON public.ground_truth USING btree (voyage_key);


-- public.runs_logging definition

-- Drop table

-- DROP TABLE runs_logging;

CREATE TABLE runs_logging (
	run_id uuid NOT NULL,
	started_at timestamptz NOT NULL,
	finished_at timestamptz NULL,
	status text NOT NULL,
	CONSTRAINT import_runs_pkey PRIMARY KEY (run_id)
);

-- public.test_generation_accuracy_logging definition

-- Drop table

-- DROP TABLE test_generation_accuracy_logging;

CREATE TABLE test_generation_accuracy_logging (
	id serial4 NOT NULL,
	run_id uuid NOT NULL,
	question_id text NOT NULL,
	generated_answer text NOT NULL,
	ground_truth_answer text NOT NULL,
	cosine_similarity numeric(6, 4) NOT NULL,
	judge_score int4 NULL,
	judge_reasoning text NULL,
	generation_ms int4 NULL,
	tested_at timestamptz DEFAULT now() NOT NULL,
	category text NULL,
	chunks jsonb NULL,
	CONSTRAINT test_generation_accuracy_logging_pkey PRIMARY KEY (id)
);
CREATE INDEX gat_question_id_idx ON public.test_generation_accuracy_logging USING btree (question_id);
CREATE INDEX gat_run_id_idx ON public.test_generation_accuracy_logging USING btree (run_id);


-- public.test_generation_run_logging definition

-- Drop table

-- DROP TABLE test_generation_run_logging;

CREATE TABLE test_generation_run_logging (
	run_id uuid NOT NULL,
	total int4 NOT NULL,
	judge_hits int4 NOT NULL,
	avg_cosine numeric(6, 4) NOT NULL,
	avg_judge_score numeric(4, 2) NOT NULL,
	run_at timestamptz DEFAULT now() NOT NULL,
	category text DEFAULT 'all'::text NOT NULL,
	flags jsonb NULL,
	CONSTRAINT test_generation_run_logging_pkey PRIMARY KEY (run_id, category)
);


-- public.test_retrieval_run_logging definition

-- Drop table

-- DROP TABLE test_retrieval_run_logging;

CREATE TABLE test_retrieval_run_logging (
	run_id uuid NOT NULL,
	test_type text NOT NULL,
	question_type text NOT NULL,
	thread_recall numeric(6, 4) NOT NULL,
	email_recall numeric(6, 4) NULL,
	total int4 NOT NULL,
	flags jsonb NOT NULL,
	run_at timestamptz DEFAULT now() NOT NULL,
	thread_hits int4 NULL,
	email_hits int4 NULL,
	CONSTRAINT test_retrieval_run_logging_pkey PRIMARY KEY (run_id, test_type, question_type),
	CONSTRAINT test_retrieval_run_logging_question_type_check CHECK ((question_type = ANY (ARRAY['fact_single'::text, 'summary'::text, 'reasoning'::text, 'unanswerable'::text, 'total'::text])))
);


-- public.thread_summaries definition

-- Drop table

-- DROP TABLE thread_summaries;

CREATE TABLE thread_summaries (
	thread_id uuid NOT NULL,
	voyage_key text NOT NULL,
	subject text NULL,
	email_count int4 NULL,
	summary text DEFAULT ''::text NOT NULL,
	status text DEFAULT 'ok'::text NOT NULL,
	log text NULL,
	generated_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT thread_summaries_pkey PRIMARY KEY (thread_id),
	CONSTRAINT thread_summaries_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text])))
);
CREATE INDEX thread_summaries_voyage_idx ON public.thread_summaries USING btree (voyage_key);


-- public.users definition

-- Drop table

-- DROP TABLE users;

CREATE TABLE users (
	username text NOT NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	password_hash text NULL,
	CONSTRAINT users_pkey PRIMARY KEY (username),
	CONSTRAINT users_username_key UNIQUE (username)
);

-- public.attachments definition

-- Drop table

-- DROP TABLE attachments;

CREATE TABLE attachments (
	id bigserial NOT NULL,
	email_id uuid NOT NULL,
	voyage_key text NOT NULL,
	file_name text NOT NULL,
	file_path text NOT NULL,
	file_type text NULL,
	size_bytes int8 NULL,
	sha256 bpchar(64) NULL,
	docling_ready bool DEFAULT false NOT NULL,
	CONSTRAINT attachments_pkey PRIMARY KEY (id),
	CONSTRAINT attachments_email_id_fkey FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE
);
CREATE INDEX attachments_email_idx ON public.attachments USING btree (email_id);
CREATE INDEX attachments_sha256_idx ON public.attachments USING btree (sha256);


-- public.chunking_logging definition

-- Drop table

-- DROP TABLE chunking_logging;

CREATE TABLE chunking_logging (
	id serial4 NOT NULL,
	source_type text NOT NULL,
	source_id text NOT NULL,
	voyage_key text NULL,
	run_id uuid NULL,
	started_at timestamptz NOT NULL,
	finished_at timestamptz NULL,
	duration_ms int4 NULL,
	status text DEFAULT 'pending'::text NOT NULL,
	n_chunks int4 NULL,
	char_count int4 NULL,
	error_message text NULL,
	total_tokens int4 NULL,
	truncated bool DEFAULT false NOT NULL,
	CONSTRAINT chunking_logging_pkey PRIMARY KEY (id),
	CONSTRAINT chunking_logging_source_type_source_id_key UNIQUE (source_type, source_id),
	CONSTRAINT chunking_logging_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE SET NULL
);


-- public.docling_logging definition

-- Drop table

-- DROP TABLE docling_logging;

CREATE TABLE docling_logging (
	sha256 bpchar(64) NOT NULL,
	file_path text NULL,
	file_type text NULL,
	file_size_bytes int8 NULL,
	started_at timestamptz NULL,
	finished_at timestamptz NULL,
	duration_ms int8 NULL,
	status text NOT NULL,
	error_message text NULL,
	char_count int4 NULL,
	token_count int4 NULL,
	gpu_util_pct int4 NULL,
	gpu_mem_pct numeric(5, 2) NULL,
	ram_pct numeric(5, 2) NULL,
	batch_idx int4 NULL,
	run_id uuid NULL,
	CONSTRAINT docling_logging_pkey PRIMARY KEY (sha256),
	CONSTRAINT docling_logging_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text, 'error'::text, 'skipped'::text]))),
	CONSTRAINT docling_logging_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE SET NULL
);
CREATE INDEX docling_logging_run_idx ON public.docling_logging USING btree (run_id);
CREATE INDEX docling_logging_status_idx ON public.docling_logging USING btree (status);


-- public.email_attach_summaries definition

-- Drop table

-- DROP TABLE email_attach_summaries;

CREATE TABLE email_attach_summaries (
	email_id uuid NOT NULL,
	voyage_key text NOT NULL,
	sent_at timestamptz NULL,
	summary text NULL,
	status text NOT NULL,
	log text NULL,
	generated_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT email_attach_summaries_pkey PRIMARY KEY (email_id),
	CONSTRAINT email_attach_summaries_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text]))),
	CONSTRAINT email_attach_summaries_email_id_fkey FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE
);
CREATE INDEX email_attach_summaries_voyage_idx ON public.email_attach_summaries USING btree (voyage_key);


-- public.email_summaries definition

-- Drop table

-- DROP TABLE email_summaries;

CREATE TABLE email_summaries (
	email_id uuid NOT NULL,
	thread_id uuid NOT NULL,
	voyage_key text NOT NULL,
	summary text DEFAULT ''::text NOT NULL,
	status text DEFAULT 'ok'::text NOT NULL,
	log text NULL,
	generated_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT email_summaries_pkey PRIMARY KEY (email_id),
	CONSTRAINT email_summaries_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text]))),
	CONSTRAINT email_summaries_email_id_fkey FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE
);
CREATE INDEX email_summaries_thread_idx ON public.email_summaries USING btree (thread_id);
CREATE INDEX email_summaries_voyage_idx ON public.email_summaries USING btree (voyage_key);


-- public.email_thread_summaries definition

-- Drop table

-- DROP TABLE email_thread_summaries;

CREATE TABLE email_thread_summaries (
	email_id uuid NOT NULL,
	thread_id uuid NOT NULL,
	voyage_key text NOT NULL,
	prior_count int4 NOT NULL,
	summary text DEFAULT ''::text NOT NULL,
	status text DEFAULT 'ok'::text NOT NULL,
	log text NULL,
	generated_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT email_thread_summaries_pkey PRIMARY KEY (email_id),
	CONSTRAINT email_thread_summaries_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'error'::text]))),
	CONSTRAINT email_thread_summaries_email_id_fkey FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE
);
CREATE INDEX email_thread_summaries_prior_count_idx ON public.email_thread_summaries USING btree (prior_count);
CREATE INDEX email_thread_summaries_thread_idx ON public.email_thread_summaries USING btree (thread_id);
CREATE INDEX email_thread_summaries_voyage_idx ON public.email_thread_summaries USING btree (voyage_key);


-- public.embedding_logging definition

-- Drop table

-- DROP TABLE embedding_logging;

CREATE TABLE embedding_logging (
	id serial4 NOT NULL,
	run_id uuid NULL,
	batch_idx int4 NOT NULL,
	n_chunks int4 NULL,
	started_at timestamptz NOT NULL,
	finished_at timestamptz NULL,
	duration_ms int4 NULL,
	status text DEFAULT 'pending'::text NOT NULL,
	error_message text NULL,
	model text NULL,
	CONSTRAINT embedding_logging_pkey PRIMARY KEY (id),
	CONSTRAINT embedding_logging_run_id_batch_idx_key UNIQUE (run_id, batch_idx),
	CONSTRAINT embedding_logging_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE SET NULL
);


-- public.ingest_logging definition

-- Drop table

-- DROP TABLE ingest_logging;

CREATE TABLE ingest_logging (
	id int8 DEFAULT nextval('file_counters_id_seq'::regclass) NOT NULL,
	run_id uuid NULL,
	voyage_key text NOT NULL,
	n_emails int8 DEFAULT 0 NULL,
	n_threads int8 DEFAULT 0 NULL,
	n_attachments int8 DEFAULT 0 NULL,
	n_bytes int8 DEFAULT 0 NULL,
	n_errors int8 DEFAULT 0 NULL,
	wall_time_ms int8 DEFAULT 0 NULL,
	CONSTRAINT file_counters_pkey PRIMARY KEY (id),
	CONSTRAINT file_counters_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE CASCADE
);


-- public.llm_logging definition

-- Drop table

-- DROP TABLE llm_logging;

CREATE TABLE llm_logging (
	sha256 bpchar(64) NOT NULL,
	file_path text NULL,
	file_type text NULL,
	char_count int4 NULL,
	size_category text NULL,
	"mode" text NULL,
	started_at timestamptz NULL,
	finished_at timestamptz NULL,
	duration_ms int8 NULL,
	status text NOT NULL,
	error_message text NULL,
	input_tokens int4 NULL,
	output_tokens int4 NULL,
	gpu_util_pct int4 NULL,
	gpu_mem_pct numeric(5, 2) NULL,
	ram_pct numeric(5, 2) NULL,
	batch_idx int4 NULL,
	run_id uuid NULL,
	CONSTRAINT llm_logging_pkey PRIMARY KEY (sha256),
	CONSTRAINT llm_logging_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'done'::text, 'error'::text, 'skipped'::text]))),
	CONSTRAINT llm_logging_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE SET NULL
);
CREATE INDEX llm_logging_run_idx ON public.llm_logging USING btree (run_id);
CREATE INDEX llm_logging_status_idx ON public.llm_logging USING btree (status);


-- public.llm_structured definition

-- Drop table

-- DROP TABLE llm_structured;

CREATE TABLE llm_structured (
	sha256 bpchar(64) NOT NULL,
	"mode" text NOT NULL,
	document_type text NULL,
	structured_md text NULL,
	input_token_count int4 DEFAULT 0 NOT NULL,
	output_token_count int4 DEFAULT 0 NOT NULL,
	model_name text NOT NULL,
	processed_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT llm_structured_mode_check CHECK ((mode = ANY (ARRAY['full'::text, 'classify'::text]))),
	CONSTRAINT llm_structured_pkey PRIMARY KEY (sha256),
	CONSTRAINT llm_structured_sha256_fkey FOREIGN KEY (sha256) REFERENCES docling(sha256) ON DELETE CASCADE
);


-- public.query_sessions definition

-- Drop table

-- DROP TABLE query_sessions;

CREATE TABLE query_sessions (
	session_id uuid DEFAULT gen_random_uuid() NOT NULL,
	username text NOT NULL,
	"source" text NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT query_sessions_new_pkey PRIMARY KEY (session_id),
	CONSTRAINT query_sessions_new_source_check CHECK ((source = ANY (ARRAY['terminal'::text, 'test'::text, 'application'::text]))),
	CONSTRAINT query_sessions_new_username_fkey FOREIGN KEY (username) REFERENCES users(username)
);


-- public.step_logging definition

-- Drop table

-- DROP TABLE step_logging;

CREATE TABLE step_logging (
	id int8 DEFAULT nextval('step_timings_id_seq'::regclass) NOT NULL,
	run_id uuid NULL,
	step_name text NOT NULL,
	started_at timestamptz NOT NULL,
	finished_at timestamptz NULL,
	duration_ms int8 NULL,
	rows_in int8 NULL,
	rows_out int8 NULL,
	errors int8 DEFAULT 0 NULL,
	notes text NULL,
	CONSTRAINT step_timings_pkey PRIMARY KEY (id),
	CONSTRAINT step_timings_run_id_fkey FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE CASCADE
);


-- public.summaries_logging definition

-- Drop table

-- DROP TABLE summaries_logging;

CREATE TABLE summaries_logging (
	id serial4 NOT NULL,
	summary_type text NOT NULL,
	entity_key text NOT NULL,
	voyage_key text NULL,
	run_id uuid NULL,
	batch_idx int4 DEFAULT 0 NOT NULL,
	started_at timestamptz NOT NULL,
	finished_at timestamptz NULL,
	duration_ms int4 NULL,
	status text DEFAULT 'pending'::text NOT NULL,
	error_message text NULL,
	input_tokens int4 NULL,
	output_tokens int4 NULL,
	CONSTRAINT summaries_logging_pkey1 PRIMARY KEY (id),
	CONSTRAINT summaries_logging_summary_type_entity_key_key UNIQUE (summary_type, entity_key),
	CONSTRAINT summaries_logging_run_id_fkey1 FOREIGN KEY (run_id) REFERENCES runs_logging(run_id) ON DELETE SET NULL
);


-- public.test_retrieval_chunk_logging definition

-- Drop table

-- DROP TABLE test_retrieval_chunk_logging;

CREATE TABLE test_retrieval_chunk_logging (
	id serial4 NOT NULL,
	run_id uuid NOT NULL,
	question_id uuid NOT NULL,
	category text NOT NULL,
	question text NOT NULL,
	thread_hit bool NOT NULL,
	thread_rank int4 NULL,
	chunks jsonb NOT NULL,
	flags jsonb NOT NULL,
	tested_at timestamptz DEFAULT now() NOT NULL,
	email_hit bool NOT NULL,
	email_rank int4 NULL,
	expected_email text NULL,
	expected_thread text NULL,
	returned_email_ids _text NOT NULL,
	returned_thread_ids _text NOT NULL,
	CONSTRAINT test_retrieval_chunk_logging_pkey PRIMARY KEY (id),
	CONSTRAINT test_retrieval_chunk_logging_question_id_fkey FOREIGN KEY (question_id) REFERENCES ground_truth(question_id)
);
CREATE INDEX chunk_log_email_hit_idx ON public.test_retrieval_chunk_logging USING btree (email_hit);
CREATE INDEX chunk_log_question_id_idx ON public.test_retrieval_chunk_logging USING btree (question_id);
CREATE INDEX chunk_log_run_id_idx ON public.test_retrieval_chunk_logging USING btree (run_id);
CREATE INDEX chunk_log_thread_hit_idx ON public.test_retrieval_chunk_logging USING btree (thread_hit);


-- public.test_retrieval_vk_logging definition

-- Drop table

-- DROP TABLE test_retrieval_vk_logging;

CREATE TABLE test_retrieval_vk_logging (
	id serial4 NOT NULL,
	run_id uuid NOT NULL,
	question_id uuid NOT NULL,
	category text NOT NULL,
	question text NOT NULL,
	expected_key text NOT NULL,
	returned_keys _text NOT NULL,
	hit bool NOT NULL,
	winner_rank int4 NULL,
	vote_counts jsonb NOT NULL,
	chunks jsonb NOT NULL,
	flags jsonb NOT NULL,
	tested_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT test_retrieval_vk_logging_pkey PRIMARY KEY (id),
	CONSTRAINT test_retrieval_vk_logging_question_id_fkey FOREIGN KEY (question_id) REFERENCES ground_truth(question_id)
);
CREATE INDEX vk_log_hit_idx ON public.test_retrieval_vk_logging USING btree (hit);
CREATE INDEX vk_log_question_id_idx ON public.test_retrieval_vk_logging USING btree (question_id);
CREATE INDEX vk_log_run_id_idx ON public.test_retrieval_vk_logging USING btree (run_id);


-- public.queries definition

-- Drop table

-- DROP TABLE queries;

CREATE TABLE queries (
	query_id uuid DEFAULT gen_random_uuid() NOT NULL,
	query_text text NOT NULL,
	username text NOT NULL,
	"source" text NOT NULL,
	session_id uuid NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT queries_new_pkey1 PRIMARY KEY (query_id),
	CONSTRAINT queries_new_source_check1 CHECK ((source = ANY (ARRAY['terminal'::text, 'test'::text, 'application'::text]))),
	CONSTRAINT queries_new_username_fkey FOREIGN KEY (username) REFERENCES users(username),
	CONSTRAINT queries_session_id_fkey FOREIGN KEY (session_id) REFERENCES query_sessions(session_id)
);


-- public.retrieval_logging definition

-- Drop table

-- DROP TABLE retrieval_logging;

CREATE TABLE retrieval_logging (
	query_id uuid NOT NULL,
	query_text text NOT NULL,
	source_types _text NULL,
	top_k_1 int4 NOT NULL,
	top_k_2 int4 NOT NULL,
	winning_keys _text NOT NULL,
	key_vote_counts jsonb NULL,
	step1_ms int4 NULL,
	step2_ms int4 NULL,
	total_ms int4 NULL,
	chunks_returned int4 NULL,
	chunks jsonb NULL,
	chunks_expanded_returned int4 NULL,
	chunks_expanded jsonb NULL,
	retrieved_source_types _text NULL,
	retrieved_source_ids _text NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	query_variants jsonb NULL,
	strategy _text NULL,
	reranked bool DEFAULT false NOT NULL,
	rerank_model text NULL,
	rerank_pool int4 NULL,
	rerank_ms int4 NULL,
	ef_search_1 int4 NULL,
	ef_search_2 int4 NULL,
	embed_input text NULL,
	CONSTRAINT retrieval_logging_new_pkey PRIMARY KEY (query_id),
	CONSTRAINT retrieval_logging_query_id_fkey FOREIGN KEY (query_id) REFERENCES queries(query_id)
);


-- public.reviews definition

-- Drop table

-- DROP TABLE reviews;

CREATE TABLE reviews (
	query_id uuid NOT NULL,
	query_text text NOT NULL,
	answer text NOT NULL,
	username text NOT NULL,
	is_correct bool NOT NULL,
	feedback text NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT reviews_pkey PRIMARY KEY (query_id),
	CONSTRAINT reviews_query_id_fkey FOREIGN KEY (query_id) REFERENCES queries(query_id),
	CONSTRAINT reviews_username_fkey FOREIGN KEY (username) REFERENCES users(username)
);


-- public.generation_logging definition

-- Drop table

-- DROP TABLE generation_logging;

CREATE TABLE generation_logging (
	query_id uuid NOT NULL,
	query_text text NOT NULL,
	answer text NOT NULL,
	system_prompt text NOT NULL,
	model text NOT NULL,
	temperature float4 NOT NULL,
	max_tokens int4 NOT NULL,
	prompt_tokens int4 NULL,
	completion_tokens int4 NULL,
	generation_ms int4 NULL,
	total_ms int4 NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	llm_input text NULL,
	CONSTRAINT generation_logging_new_pkey PRIMARY KEY (query_id),
	CONSTRAINT generation_logging_query_id_fkey FOREIGN KEY (query_id) REFERENCES queries(query_id)
);


-- public.docling_load_queue source

CREATE OR REPLACE VIEW docling_load_queue
AS SELECT DISTINCT ON (sha256) sha256,
    email_id,
    voyage_key,
    file_path,
    file_type
   FROM attachments
  WHERE sha256 IS NOT NULL AND docling_ready = true AND (size_bytes IS NULL OR size_bytes < 5242880)
  ORDER BY sha256;

-- public.llm_load_queue source

CREATE OR REPLACE VIEW llm_load_queue
AS SELECT DISTINCT ON (d.sha256) d.sha256,
    d.markdown,
    d.char_count,
    d.token_count,
    a.email_id,
    a.voyage_key,
    a.file_path,
    a.file_type
   FROM docling d
     JOIN attachments a ON a.sha256 = d.sha256
  WHERE d.markdown IS NOT NULL AND length(regexp_replace(d.markdown, '<!--[^>]*-->|\s+'::text, ''::text, 'g'::text)) >= 50
  ORDER BY d.sha256;

-- public.operator_queries_v source

CREATE OR REPLACE VIEW operator_queries_v
AS SELECT query_id,
    query_text,
    username,
    source,
    session_id,
    created_at
   FROM queries
  WHERE lower(username) <> ALL (ARRAY['nsl'::text, 'dev'::text, 'developer'::text]);
