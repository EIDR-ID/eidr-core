--
-- PostgreSQL database dump
--

\restrict ND6TMzV8NxXxtxrFjEGDgHbQdtqZh8i5jfiIVxCcWPNmIvvJB98suTklwOvwqbP


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;


--
-- Name: EXTENSION pg_stat_statements; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_stat_statements IS 'track planning and execution statistics of all SQL statements executed';


--
-- Name: pgstattuple; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgstattuple WITH SCHEMA public;


--
-- Name: EXTENSION pgstattuple; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgstattuple IS 'show tuple-level statistics';


--
-- Name: get_exact_table_counts(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_exact_table_counts() RETURNS TABLE(schema_name text, table_name text, exact_row_count bigint)
    LANGUAGE plpgsql
    AS $$

DECLARE

    rec RECORD;

BEGIN

    FOR rec IN 

        SELECT table_schema, t.table_name 

        FROM information_schema.tables t

        WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema') 

          AND t.table_type = 'BASE TABLE'

    LOOP

        schema_name := rec.table_schema;

        table_name := rec.table_name;

        

        EXECUTE format('SELECT count(*) FROM %I.%I', rec.table_schema, rec.table_name) 

        INTO exact_row_count;

        

        RETURN NEXT;

    END LOOP;

END;

$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alias_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alias_log (
    id integer NOT NULL,
    content_id text NOT NULL,
    creation_type text NOT NULL,
    logged_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: alias_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alias_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alias_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alias_log_id_seq OWNED BY public.alias_log.id;


--
-- Name: classes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.classes (
    content_id text NOT NULL,
    class text,
    order_index integer NOT NULL
);


--
-- Name: clips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clips (
    content_id text NOT NULL,
    parent_id text,
    components_mode text,
    start text,
    start_timecode text,
    duration text,
    duration_timecode text
);


--
-- Name: compilation_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compilation_entries (
    content_id text NOT NULL,
    entry_number text,
    entry_class text,
    display_name text,
    referenced_id text,
    order_index integer NOT NULL
);


--
-- Name: compilations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compilations (
    content_id text NOT NULL,
    compilation_class text,
    has_other_inclusions boolean
);


--
-- Name: composite_elements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.composite_elements (
    content_id text NOT NULL,
    element_id text,
    components_mode text,
    source_start text,
    source_start_timecode text,
    source_duration text,
    source_duration_timecode text,
    destination_start text,
    destination_start_timecode text,
    destination_duration text,
    destination_duration_timecode text,
    order_index integer NOT NULL,
    description text
);


--
-- Name: composites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.composites (
    content_id text NOT NULL,
    composite_class text
);


--
-- Name: content_alternate_ids; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_alternate_ids (
    content_id text NOT NULL,
    alt_id text NOT NULL,
    id_type text NOT NULL,
    domain text,
    relation text,
    order_index integer NOT NULL
)
WITH (autovacuum_enabled='true', autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_alternate_ids_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_alternate_ids_self (
    content_id text NOT NULL,
    alt_id text NOT NULL,
    id_type text NOT NULL,
    domain text,
    relation text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_associated_org_names; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_associated_org_names (
    content_id text NOT NULL,
    org_index integer NOT NULL,
    name text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_associated_org_names_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_associated_org_names_self (
    content_id text NOT NULL,
    org_index integer NOT NULL,
    name text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_associated_orgs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_associated_orgs (
    content_id text NOT NULL,
    party_id text,
    display_name text,
    role text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_associated_orgs_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_associated_orgs_self (
    content_id text NOT NULL,
    party_id text,
    display_name text,
    role text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_core; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_core (
    content_id text NOT NULL,
    structural_type text,
    mode text,
    referent_type text,
    title text,
    title_lang text,
    title_class text,
    system_generated boolean,
    release_date date,
    release_year integer,
    status text,
    approximate_length text,
    length_timecode text,
    length_minutes integer,
    registrant_extra text,
    description text,
    description_lang text,
    target_id text
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_core_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_core_self (
    content_id text NOT NULL,
    structural_type text,
    mode text,
    referent_type text,
    title text,
    title_lang text,
    title_class text,
    system_generated boolean,
    release_date date,
    release_year integer,
    status text,
    approximate_length text,
    length_timecode text,
    length_minutes integer,
    registrant_extra text,
    description text,
    description_lang text,
    target_id text
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_countries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_countries (
    content_id text NOT NULL,
    country_code text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_countries_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_countries_self (
    content_id text NOT NULL,
    country_code text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_credits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_credits (
    content_id text NOT NULL,
    role text NOT NULL,
    name text,
    sort_name text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_credits_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_credits_self (
    content_id text NOT NULL,
    role text NOT NULL,
    name text,
    sort_name text,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_languages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_languages (
    content_id text NOT NULL,
    lang text,
    mode text,
    is_original boolean NOT NULL,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_languages_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_languages_self (
    content_id text NOT NULL,
    lang text,
    mode text,
    is_original boolean NOT NULL,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_metadata_authorities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_metadata_authorities (
    content_id text NOT NULL,
    party_id text,
    order_index integer NOT NULL
);


--
-- Name: content_metadata_authorities_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_metadata_authorities_self (
    content_id text NOT NULL,
    party_id text,
    order_index integer NOT NULL
);


--
-- Name: content_provenance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_provenance (
    content_id text NOT NULL,
    txn_id integer,
    issue_number integer,
    status text,
    registrant text,
    creation_date date,
    creation_time time without time zone,
    last_modification_date date,
    last_modification_time time without time zone,
    publication_date date,
    publication_time time without time zone
);


--
-- Name: content_titles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_titles (
    content_id text NOT NULL,
    title text,
    title_lang text,
    title_class text,
    system_generated boolean,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: content_titles_self; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_titles_self (
    content_id text NOT NULL,
    title text,
    title_lang text,
    title_class text,
    system_generated boolean,
    order_index integer NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.02', autovacuum_analyze_scale_factor='0.01', autovacuum_vacuum_threshold='5000', autovacuum_analyze_threshold='5000');


--
-- Name: details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.details (
    content_id text NOT NULL,
    detail text,
    domain text,
    order_index integer NOT NULL
);


--
-- Name: diagnostic_failures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_failures (
    failure_id integer NOT NULL,
    id_type text NOT NULL,
    identifier text NOT NULL,
    error_msg text NOT NULL,
    ingest_phase text NOT NULL,
    first_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    failure_count integer DEFAULT 1 NOT NULL,
    CONSTRAINT diagnostic_failures_id_type_check CHECK ((id_type = ANY (ARRAY['Content'::text, 'Party'::text, 'Service'::text]))),
    CONSTRAINT diagnostic_failures_ingest_phase_check CHECK ((ingest_phase = ANY (ARRAY['bulk'::text, 'mirror'::text, 'catchup'::text])))
);


--
-- Name: diagnostic_failures_failure_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_failures_failure_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_failures_failure_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_failures_failure_id_seq OWNED BY public.diagnostic_failures.failure_id;


--
-- Name: diagnostics_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostics_log (
    id integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now(),
    content_id text,
    txn_id integer,
    level text,
    module text,
    function text,
    message text
);


--
-- Name: diagnostics_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostics_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostics_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostics_log_id_seq OWNED BY public.diagnostics_log.id;


--
-- Name: edits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edits (
    content_id text NOT NULL,
    parent_id text,
    edit_use text,
    color_type text,
    three_d boolean
);


--
-- Name: episode_numbers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.episode_numbers (
    content_id text NOT NULL,
    number text,
    domain text,
    type text NOT NULL,
    order_index integer NOT NULL
);


--
-- Name: episodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.episodes (
    content_id text NOT NULL,
    parent_id text,
    episode_class text,
    distribution_number text,
    house_sequence text,
    time_slot text
);


--
-- Name: lightweight_relationships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lightweight_relationships (
    content_id text NOT NULL,
    target_id text,
    type text,
    class text,
    order_index integer NOT NULL
);


--
-- Name: manifestation_digital; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manifestation_digital (
    content_id text NOT NULL,
    xml_block text
);


--
-- Name: manifestations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manifestations (
    content_id text NOT NULL,
    parent_id text
);


--
-- Name: mirror_scheduler; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mirror_scheduler (
    id integer NOT NULL,
    last_run_time timestamp with time zone,
    next_run_time timestamp with time zone,
    last_txn_id bigint,
    status text,
    notes text,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: mirror_scheduler_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mirror_scheduler_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mirror_scheduler_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mirror_scheduler_id_seq OWNED BY public.mirror_scheduler.id;


--
-- Name: party_core; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.party_core (
    party_id text NOT NULL,
    account_name text,
    display_name text,
    sort_name text,
    active boolean,
    allowed_roles text[],
    status text,
    target_id text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: party_names; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.party_names (
    party_id text NOT NULL,
    name text,
    type text NOT NULL,
    order_index integer NOT NULL
);


--
-- Name: raw_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_records (
    txn_id bigint NOT NULL,
    xml_payload text,
    "timestamp" timestamp without time zone
)
WITH (autovacuum_analyze_scale_factor='0.01', autovacuum_analyze_threshold='10000');


--
-- Name: recon_checkpoint; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recon_checkpoint (
    entity_type text NOT NULL,
    last_checked timestamp with time zone NOT NULL,
    notes text
);


--
-- Name: regions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.regions (
    content_id text NOT NULL,
    region text,
    order_index integer NOT NULL
);


--
-- Name: report_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_log (
    id integer NOT NULL,
    report_type text NOT NULL,
    sent_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    notes text
);


--
-- Name: report_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.report_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: report_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.report_log_id_seq OWNED BY public.report_log.id;


--
-- Name: seasons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.seasons (
    content_id text NOT NULL,
    parent_id text,
    end_date date,
    end_year integer,
    season_class text,
    number_required boolean,
    date_required boolean,
    original_title_required boolean,
    sequence_number integer
);


--
-- Name: series; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.series (
    content_id text NOT NULL,
    end_date date,
    end_year integer,
    series_class text,
    number_required boolean,
    date_required boolean,
    original_title_required boolean
);


--
-- Name: service_affiliations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_affiliations (
    service_id text NOT NULL,
    affiliated_id text,
    order_index integer NOT NULL
);


--
-- Name: service_alternate_ids; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_alternate_ids (
    service_id text NOT NULL,
    alt_id text,
    domain text,
    order_index integer NOT NULL
);


--
-- Name: service_core; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_core (
    service_id text NOT NULL,
    display_name text,
    description text,
    active boolean,
    primary_audio_language text,
    primary_time_zone text,
    delivery_model text[],
    parent_id text,
    status text,
    target_id text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: service_names; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_names (
    service_id text NOT NULL,
    name text,
    abbreviation boolean DEFAULT false,
    type text NOT NULL,
    order_index integer NOT NULL,
    CONSTRAINT service_names_type_check CHECK ((type = ANY (ARRAY['display'::text, 'alternate'::text])))
);


--
-- Name: temp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.temp (
    content_id text NOT NULL
);


--
-- Name: alias_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alias_log ALTER COLUMN id SET DEFAULT nextval('public.alias_log_id_seq'::regclass);


--
-- Name: diagnostic_failures failure_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_failures ALTER COLUMN failure_id SET DEFAULT nextval('public.diagnostic_failures_failure_id_seq'::regclass);


--
-- Name: diagnostics_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostics_log ALTER COLUMN id SET DEFAULT nextval('public.diagnostics_log_id_seq'::regclass);


--
-- Name: mirror_scheduler id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mirror_scheduler ALTER COLUMN id SET DEFAULT nextval('public.mirror_scheduler_id_seq'::regclass);


--
-- Name: report_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_log ALTER COLUMN id SET DEFAULT nextval('public.report_log_id_seq'::regclass);


--
-- Name: alias_log alias_log_content_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alias_log
    ADD CONSTRAINT alias_log_content_id_key UNIQUE (content_id);


--
-- Name: alias_log alias_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alias_log
    ADD CONSTRAINT alias_log_pkey PRIMARY KEY (id);


--
-- Name: classes classes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.classes
    ADD CONSTRAINT classes_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: clips clips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clips
    ADD CONSTRAINT clips_pkey PRIMARY KEY (content_id);


--
-- Name: compilation_entries compilation_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compilation_entries
    ADD CONSTRAINT compilation_entries_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: compilations compilations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compilations
    ADD CONSTRAINT compilations_pkey PRIMARY KEY (content_id);


--
-- Name: composite_elements composite_elements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.composite_elements
    ADD CONSTRAINT composite_elements_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: composites composites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.composites
    ADD CONSTRAINT composites_pkey PRIMARY KEY (content_id);


--
-- Name: content_alternate_ids content_alternate_ids_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_alternate_ids
    ADD CONSTRAINT content_alternate_ids_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_alternate_ids_self content_alternate_ids_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_alternate_ids_self
    ADD CONSTRAINT content_alternate_ids_self_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_associated_org_names content_associated_org_names_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_org_names
    ADD CONSTRAINT content_associated_org_names_pkey PRIMARY KEY (content_id, org_index, order_index);


--
-- Name: content_associated_org_names_self content_associated_org_names_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_org_names_self
    ADD CONSTRAINT content_associated_org_names_self_pkey PRIMARY KEY (content_id, org_index, order_index);


--
-- Name: content_associated_orgs content_associated_orgs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_orgs
    ADD CONSTRAINT content_associated_orgs_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_associated_orgs_self content_associated_orgs_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_orgs_self
    ADD CONSTRAINT content_associated_orgs_self_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_core content_core_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_core
    ADD CONSTRAINT content_core_pkey PRIMARY KEY (content_id);


--
-- Name: content_core_self content_core_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_core_self
    ADD CONSTRAINT content_core_self_pkey PRIMARY KEY (content_id);


--
-- Name: content_countries content_countries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_countries
    ADD CONSTRAINT content_countries_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_countries_self content_countries_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_countries_self
    ADD CONSTRAINT content_countries_self_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_credits content_credits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_credits
    ADD CONSTRAINT content_credits_pkey PRIMARY KEY (content_id, role, order_index);


--
-- Name: content_credits_self content_credits_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_credits_self
    ADD CONSTRAINT content_credits_self_pkey PRIMARY KEY (content_id, role, order_index);


--
-- Name: content_languages content_languages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_languages
    ADD CONSTRAINT content_languages_pkey PRIMARY KEY (content_id, order_index, is_original);


--
-- Name: content_languages_self content_languages_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_languages_self
    ADD CONSTRAINT content_languages_self_pkey PRIMARY KEY (content_id, order_index, is_original);


--
-- Name: content_metadata_authorities content_metadata_authorities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_metadata_authorities
    ADD CONSTRAINT content_metadata_authorities_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_metadata_authorities_self content_metadata_authorities_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_metadata_authorities_self
    ADD CONSTRAINT content_metadata_authorities_self_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_provenance content_provenance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_provenance
    ADD CONSTRAINT content_provenance_pkey PRIMARY KEY (content_id);


--
-- Name: content_titles content_titles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_titles
    ADD CONSTRAINT content_titles_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: content_titles_self content_titles_self_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_titles_self
    ADD CONSTRAINT content_titles_self_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: details details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.details
    ADD CONSTRAINT details_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: diagnostic_failures diagnostic_failures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_failures
    ADD CONSTRAINT diagnostic_failures_pkey PRIMARY KEY (failure_id);


--
-- Name: diagnostics_log diagnostics_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostics_log
    ADD CONSTRAINT diagnostics_log_pkey PRIMARY KEY (id);


--
-- Name: edits edits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edits
    ADD CONSTRAINT edits_pkey PRIMARY KEY (content_id);


--
-- Name: episode_numbers episode_numbers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.episode_numbers
    ADD CONSTRAINT episode_numbers_pkey PRIMARY KEY (content_id, type, order_index);


--
-- Name: episodes episodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.episodes
    ADD CONSTRAINT episodes_pkey PRIMARY KEY (content_id);


--
-- Name: lightweight_relationships lightweight_relationships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lightweight_relationships
    ADD CONSTRAINT lightweight_relationships_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: manifestation_digital manifestation_digital_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manifestation_digital
    ADD CONSTRAINT manifestation_digital_pkey PRIMARY KEY (content_id);


--
-- Name: manifestations manifestations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manifestations
    ADD CONSTRAINT manifestations_pkey PRIMARY KEY (content_id);


--
-- Name: mirror_scheduler mirror_scheduler_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mirror_scheduler
    ADD CONSTRAINT mirror_scheduler_pkey PRIMARY KEY (id);


--
-- Name: party_core party_core_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.party_core
    ADD CONSTRAINT party_core_pkey PRIMARY KEY (party_id);


--
-- Name: party_names party_names_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.party_names
    ADD CONSTRAINT party_names_pkey PRIMARY KEY (party_id, type, order_index);


--
-- Name: raw_records raw_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_records
    ADD CONSTRAINT raw_records_pkey PRIMARY KEY (txn_id);


--
-- Name: recon_checkpoint recon_checkpoint_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recon_checkpoint
    ADD CONSTRAINT recon_checkpoint_pkey PRIMARY KEY (entity_type);


--
-- Name: regions regions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regions
    ADD CONSTRAINT regions_pkey PRIMARY KEY (content_id, order_index);


--
-- Name: report_log report_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_log
    ADD CONSTRAINT report_log_pkey PRIMARY KEY (id);


--
-- Name: seasons seasons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.seasons
    ADD CONSTRAINT seasons_pkey PRIMARY KEY (content_id);


--
-- Name: series series_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.series
    ADD CONSTRAINT series_pkey PRIMARY KEY (content_id);


--
-- Name: service_affiliations service_affiliations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_affiliations
    ADD CONSTRAINT service_affiliations_pkey PRIMARY KEY (service_id, order_index);


--
-- Name: service_alternate_ids service_alternate_ids_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_alternate_ids
    ADD CONSTRAINT service_alternate_ids_pkey PRIMARY KEY (service_id, order_index);


--
-- Name: service_core service_core_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_core
    ADD CONSTRAINT service_core_pkey PRIMARY KEY (service_id);


--
-- Name: service_names service_names_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_names
    ADD CONSTRAINT service_names_pkey PRIMARY KEY (service_id, type, order_index);


--
-- Name: clips_parent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX clips_parent_id_idx ON public.clips USING btree (parent_id);


--
-- Name: diagnostics_log_content_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX diagnostics_log_content_id_idx ON public.diagnostics_log USING btree (content_id);


--
-- Name: diagnostics_log_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX diagnostics_log_timestamp_idx ON public.diagnostics_log USING btree ("timestamp");


--
-- Name: edits_parent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX edits_parent_id_idx ON public.edits USING btree (parent_id);


--
-- Name: episodes_parent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX episodes_parent_id_idx ON public.episodes USING btree (parent_id);


--
-- Name: idx_alias_log_logged_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alias_log_logged_at ON public.alias_log USING btree (logged_at DESC);


--
-- Name: idx_alt_ids_is_same_as; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alt_ids_is_same_as ON public.content_alternate_ids USING btree (content_id, id_type, domain) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_alt_ids_self_is_same_as; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alt_ids_self_is_same_as ON public.content_alternate_ids_self USING btree (content_id, id_type, domain) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_assoc_org_names_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assoc_org_names_content_id_ord ON public.content_associated_org_names USING btree (content_id, order_index);


--
-- Name: idx_assoc_org_names_self_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assoc_org_names_self_content_id_ord ON public.content_associated_org_names_self USING btree (content_id, order_index);


--
-- Name: idx_assoc_orgs_role_cont; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assoc_orgs_role_cont ON public.content_associated_orgs USING btree (role, content_id);


--
-- Name: idx_cai_content_type_domain_relnorm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cai_content_type_domain_relnorm ON public.content_alternate_ids USING btree (content_id, id_type, domain, COALESCE(relation, 'IsSameAs'::text)) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_cai_type_domain_relnorm_altid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cai_type_domain_relnorm_altid ON public.content_alternate_ids USING btree (id_type, domain, COALESCE(relation, 'IsSameAs'::text), alt_id) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_cais_content_type_domain_relnorm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cais_content_type_domain_relnorm ON public.content_alternate_ids_self USING btree (content_id, id_type, domain, COALESCE(relation, 'IsSameAs'::text)) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_cais_type_domain_relnorm_altid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cais_type_domain_relnorm_altid ON public.content_alternate_ids_self USING btree (id_type, domain, COALESCE(relation, 'IsSameAs'::text), alt_id) WHERE ((relation IS NULL) OR (relation = 'IsSameAs'::text));


--
-- Name: idx_compilation_entry_ref; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_compilation_entry_ref ON public.compilation_entries USING btree (referenced_id);


--
-- Name: idx_composite_element_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_composite_element_target ON public.composite_elements USING btree (element_id);


--
-- Name: idx_content_alt_ids_alt_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alt_ids_alt_id ON public.content_alternate_ids USING btree (alt_id);


--
-- Name: idx_content_alt_ids_self_alt_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alt_ids_self_alt_id ON public.content_alternate_ids_self USING btree (alt_id);


--
-- Name: idx_content_alternate_ids_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alternate_ids_domain ON public.content_alternate_ids USING btree (domain);


--
-- Name: idx_content_alternate_ids_id_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alternate_ids_id_type ON public.content_alternate_ids USING btree (id_type);


--
-- Name: idx_content_alternate_ids_self_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alternate_ids_self_domain ON public.content_alternate_ids_self USING btree (domain);


--
-- Name: idx_content_alternate_ids_self_id_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_alternate_ids_self_id_type ON public.content_alternate_ids_self USING btree (id_type);


--
-- Name: idx_content_altids_self_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_altids_self_content_id_ord ON public.content_alternate_ids_self USING btree (content_id, order_index);


--
-- Name: idx_content_core_content_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_content_id ON public.content_core USING btree (content_id);


--
-- Name: idx_content_core_length_minutes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_length_minutes ON public.content_core USING btree (length_minutes);


--
-- Name: idx_content_core_lengths; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_lengths ON public.content_core USING btree (approximate_length, length_timecode);


--
-- Name: idx_content_core_referent_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_referent_type ON public.content_core USING btree (referent_type);


--
-- Name: idx_content_core_release; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_release ON public.content_core USING btree (release_date);


--
-- Name: idx_content_core_release_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_release_year ON public.content_core USING btree (release_year);


--
-- Name: idx_content_core_self_content_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_self_content_id ON public.content_core_self USING btree (content_id);


--
-- Name: idx_content_core_self_referent_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_self_referent_type ON public.content_core_self USING btree (referent_type);


--
-- Name: idx_content_core_self_release_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_self_release_year ON public.content_core_self USING btree (release_year);


--
-- Name: idx_content_core_self_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_self_status ON public.content_core_self USING btree (status);


--
-- Name: idx_content_core_self_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_self_target_id ON public.content_core_self USING btree (target_id);


--
-- Name: idx_content_core_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_status ON public.content_core USING btree (status);


--
-- Name: idx_content_core_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_core_target_id ON public.content_core USING btree (target_id);


--
-- Name: idx_content_countries_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_countries_content_id_ord ON public.content_countries USING btree (content_id, order_index);


--
-- Name: idx_content_countries_self_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_countries_self_content_id_ord ON public.content_countries_self USING btree (content_id, order_index);


--
-- Name: idx_content_credits_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_credits_content_id_ord ON public.content_credits USING btree (content_id, order_index);


--
-- Name: idx_content_credits_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_credits_role ON public.content_credits USING btree (role);


--
-- Name: idx_content_credits_self_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_credits_self_content_id_ord ON public.content_credits_self USING btree (content_id, order_index);


--
-- Name: idx_content_credits_self_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_credits_self_role ON public.content_credits_self USING btree (role);


--
-- Name: idx_content_languages_version_lang; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_languages_version_lang ON public.content_languages USING btree (lang) WHERE (((is_original IS FALSE) OR (is_original IS NULL)) AND (lang IS NOT NULL));


--
-- Name: idx_content_metadata_auth_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_metadata_auth_content_id_ord ON public.content_metadata_authorities USING btree (content_id, order_index);


--
-- Name: idx_content_metadata_auth_self_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_metadata_auth_self_content_id_ord ON public.content_metadata_authorities_self USING btree (content_id, order_index);


--
-- Name: idx_content_prov_creation_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_prov_creation_date ON public.content_provenance USING btree (creation_date);


--
-- Name: idx_content_prov_issue_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_prov_issue_number ON public.content_provenance USING btree (issue_number);


--
-- Name: idx_content_prov_publication_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_prov_publication_date ON public.content_provenance USING btree (publication_date);


--
-- Name: idx_content_prov_registrant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_prov_registrant ON public.content_provenance USING btree (registrant);


--
-- Name: idx_content_provenance_content_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_provenance_content_id ON public.content_provenance USING btree (content_id);


--
-- Name: idx_content_provenance_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_provenance_status ON public.content_provenance USING btree (status);


--
-- Name: idx_content_provenance_txn_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_provenance_txn_id ON public.content_provenance USING btree (txn_id);


--
-- Name: idx_content_titles_self_title_lang_nonsystem; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_titles_self_title_lang_nonsystem ON public.content_titles_self USING btree (title_lang) WHERE ((system_generated IS FALSE) AND (title_lang IS NOT NULL));


--
-- Name: idx_countries_self_cid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_countries_self_cid ON public.content_countries_self USING btree (content_id, order_index);


--
-- Name: idx_cp_content_create; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cp_content_create ON public.content_provenance USING btree (content_id, creation_date);


--
-- Name: idx_cp_content_pub_issue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cp_content_pub_issue ON public.content_provenance USING btree (content_id, publication_date, issue_number);


--
-- Name: idx_credits_role_content; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credits_role_content ON public.content_credits USING btree (role, content_id);


--
-- Name: idx_lightweight_rels_content_id_ord; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lightweight_rels_content_id_ord ON public.lightweight_relationships USING btree (content_id, order_index);


--
-- Name: idx_lightweight_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lightweight_target ON public.lightweight_relationships USING btree (target_id);


--
-- Name: idx_mirror_scheduler_last_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mirror_scheduler_last_run ON public.mirror_scheduler USING btree (last_run_time DESC);


--
-- Name: idx_orgs_full_cid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orgs_full_cid ON public.content_associated_orgs USING btree (content_id);


--
-- Name: idx_party_core_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_party_core_status ON public.party_core USING btree (status);


--
-- Name: idx_party_core_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_party_core_target_id ON public.party_core USING btree (target_id);


--
-- Name: idx_raw_records_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_raw_records_timestamp ON public.raw_records USING btree ("timestamp");


--
-- Name: idx_report_log_type_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_report_log_type_time ON public.report_log USING btree (report_type, sent_time DESC);


--
-- Name: idx_series_content_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_series_content_id ON public.series USING btree (content_id);


--
-- Name: idx_service_core_delivery_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_service_core_delivery_model ON public.service_core USING gin (delivery_model);


--
-- Name: idx_service_core_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_service_core_status ON public.service_core USING btree (status);


--
-- Name: idx_service_core_target_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_service_core_target_id ON public.service_core USING btree (target_id);


--
-- Name: idx_titles_self_sysgen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_titles_self_sysgen ON public.content_titles_self USING btree (system_generated);


--
-- Name: manifestations_parent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX manifestations_parent_id_idx ON public.manifestations USING btree (parent_id);


--
-- Name: seasons_parent_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX seasons_parent_id_idx ON public.seasons USING btree (parent_id);


--
-- Name: content_associated_org_names content_associated_org_names_content_id_org_index_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_org_names
    ADD CONSTRAINT content_associated_org_names_content_id_org_index_fkey FOREIGN KEY (content_id, org_index) REFERENCES public.content_associated_orgs(content_id, order_index) ON DELETE CASCADE;


--
-- Name: content_associated_org_names_self content_associated_org_names_self_content_id_org_index_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_org_names_self
    ADD CONSTRAINT content_associated_org_names_self_content_id_org_index_fkey FOREIGN KEY (content_id, org_index) REFERENCES public.content_associated_orgs_self(content_id, order_index) ON DELETE CASCADE;


--
-- Name: content_associated_orgs content_associated_orgs_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_orgs
    ADD CONSTRAINT content_associated_orgs_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_associated_orgs_self content_associated_orgs_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_associated_orgs_self
    ADD CONSTRAINT content_associated_orgs_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: content_countries content_countries_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_countries
    ADD CONSTRAINT content_countries_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_countries_self content_countries_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_countries_self
    ADD CONSTRAINT content_countries_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: content_credits content_credits_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_credits
    ADD CONSTRAINT content_credits_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_credits_self content_credits_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_credits_self
    ADD CONSTRAINT content_credits_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: content_languages content_languages_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_languages
    ADD CONSTRAINT content_languages_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_languages_self content_languages_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_languages_self
    ADD CONSTRAINT content_languages_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: content_metadata_authorities content_metadata_authorities_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_metadata_authorities
    ADD CONSTRAINT content_metadata_authorities_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_metadata_authorities_self content_metadata_authorities_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_metadata_authorities_self
    ADD CONSTRAINT content_metadata_authorities_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: content_provenance content_provenance_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_provenance
    ADD CONSTRAINT content_provenance_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_titles content_titles_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_titles
    ADD CONSTRAINT content_titles_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core(content_id) ON DELETE CASCADE;


--
-- Name: content_titles_self content_titles_self_content_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_titles_self
    ADD CONSTRAINT content_titles_self_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content_core_self(content_id) ON DELETE CASCADE;


--
-- Name: party_names party_names_party_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.party_names
    ADD CONSTRAINT party_names_party_id_fkey FOREIGN KEY (party_id) REFERENCES public.party_core(party_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict ND6TMzV8NxXxtxrFjEGDgHbQdtqZh8i5jfiIVxCcWPNmIvvJB98suTklwOvwqbP
