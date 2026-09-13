--
-- PostgreSQL database dump
--

\restrict CHh2Vu07rvgIMR3pVYMPAUjuhYqlwWd9dIzMjMBiZapbW6qcpSeH8p2Mh3Lwang


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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: altid_pull; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.altid_pull (
    pull_id integer NOT NULL,
    pulled_at timestamp with time zone DEFAULT now() NOT NULL,
    source text NOT NULL,
    row_count bigint,
    notes text
);


--
-- Name: backfill_checked; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backfill_checked (
    pull_id integer NOT NULL,
    eidr_id text NOT NULL,
    found integer NOT NULL,
    checked_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: correction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.correction (
    pull_id integer NOT NULL,
    eidr_id text NOT NULL,
    imdb_id text NOT NULL,
    op text NOT NULL,
    relation text,
    reason text NOT NULL,
    applied_at timestamp with time zone,
    apply_status text,
    apply_detail text
);


--
-- Name: crosswalk_class; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crosswalk_class (
    pull_id integer NOT NULL,
    snapshot_id smallint NOT NULL,
    eidr_id text NOT NULL,
    imdb_id text NOT NULL,
    relation text,
    existence text NOT NULL,
    remapped_to text,
    target_present boolean,
    eidr_count integer NOT NULL,
    companion_present boolean,
    action text NOT NULL,
    classified_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: eidr_imdb_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eidr_imdb_link (
    pull_id integer NOT NULL,
    eidr_id text NOT NULL,
    imdb_id text NOT NULL,
    id_type text,
    domain text,
    relation text,
    order_index integer
);


--
-- Name: eidr_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.eidr_record (
    pull_id integer NOT NULL,
    eidr_id text NOT NULL,
    structural_type text,
    referent_type text,
    mode text,
    title text,
    release_year integer,
    status text,
    length_minutes integer,
    parent_id text
);


--
-- Name: entity_hash; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_hash (
    snapshot_id smallint NOT NULL,
    kind character(1) NOT NULL,
    entity_id text NOT NULL,
    row_hash bytea NOT NULL
);


--
-- Name: episode_info; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.episode_info (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    series_title_id text NOT NULL,
    season_number integer,
    episode_number integer
);


--
-- Name: ingest_reject; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingest_reject (
    snapshot_id smallint NOT NULL,
    kind character(1) NOT NULL,
    entity_id text,
    rule text NOT NULL,
    detail text,
    raw jsonb
);


--
-- Name: live_probe; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.live_probe (
    imdb_id text NOT NULL,
    probed_at timestamp with time zone DEFAULT now() NOT NULL,
    state text NOT NULL,
    verdict text NOT NULL,
    title_type text,
    title text,
    year integer,
    rank integer,
    detail text
);


--
-- Name: name; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.name (
    snapshot_id smallint NOT NULL,
    name_id text NOT NULL,
    name text NOT NULL,
    remapped_to text,
    death_date date,
    death_status text,
    row_hash bytea NOT NULL,
    rest jsonb
);


--
-- Name: public_aka; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_aka (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    ordering integer NOT NULL,
    title text,
    region text,
    language text,
    types text,
    attributes text,
    is_original_title boolean
);


--
-- Name: public_crew; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_crew (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    role text NOT NULL,
    seq smallint NOT NULL,
    nconst text NOT NULL
);


--
-- Name: public_episode; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_episode (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    parent_tconst text,
    season_number integer,
    episode_number integer
);


--
-- Name: public_genre; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_genre (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    seq smallint NOT NULL,
    genre text NOT NULL
);


--
-- Name: public_known_for; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_known_for (
    public_snapshot_id smallint NOT NULL,
    nconst text NOT NULL,
    seq smallint NOT NULL,
    tconst text NOT NULL
);


--
-- Name: public_name; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_name (
    public_snapshot_id smallint NOT NULL,
    nconst text NOT NULL,
    primary_name text,
    birth_year smallint,
    death_year smallint,
    primary_profession text,
    known_for_titles text
);


--
-- Name: public_principal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_principal (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    ordering integer NOT NULL,
    nconst text NOT NULL,
    category text,
    job text,
    characters text
);


--
-- Name: public_profession; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_profession (
    public_snapshot_id smallint NOT NULL,
    nconst text NOT NULL,
    seq smallint NOT NULL,
    profession text NOT NULL
);


--
-- Name: public_rating; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_rating (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    average_rating numeric(3,1),
    num_votes integer
);


--
-- Name: public_reject; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_reject (
    public_snapshot_id smallint NOT NULL,
    dataset text NOT NULL,
    line_no bigint,
    entity_id text,
    rule text NOT NULL,
    detail text,
    raw text
);


--
-- Name: public_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_snapshot (
    public_snapshot_id smallint NOT NULL,
    label text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    source_date date,
    source_dir text,
    per_file jsonb,
    status text DEFAULT 'loading'::text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    notes text
);


--
-- Name: public_title; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_title (
    public_snapshot_id smallint NOT NULL,
    tconst text NOT NULL,
    title_type text,
    primary_title text,
    original_title text,
    is_adult boolean,
    start_year smallint,
    end_year smallint,
    runtime_minutes integer,
    genres text
);


--
-- Name: series_info; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.series_info (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    start_year smallint,
    end_year smallint,
    episode_count integer
);


--
-- Name: shape_shared; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shape_shared (
    pull_id integer NOT NULL,
    imdb_id text NOT NULL,
    imdb_type text,
    n_eidr integer NOT NULL,
    n_child integer NOT NULL,
    n_short integer NOT NULL,
    n_series integer NOT NULL,
    shape text NOT NULL
);


--
-- Name: snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.snapshot (
    snapshot_id smallint NOT NULL,
    label text NOT NULL,
    title_file text,
    name_file text,
    published_date date,
    title_count bigint,
    name_count bigint,
    status text DEFAULT 'loading'::text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    notes text
);


--
-- Name: title; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    title_type text NOT NULL,
    original_title text NOT NULL,
    year smallint,
    runtime_minutes integer,
    is_adult boolean DEFAULT false NOT NULL,
    remapped_to text,
    imdb_url text,
    row_hash bytea NOT NULL,
    rest jsonb
);


--
-- Name: title_aka; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_aka (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    title text NOT NULL,
    language text,
    country text
);


--
-- Name: title_company; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_company (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    bucket text NOT NULL,
    seq smallint NOT NULL,
    company_id text,
    name text,
    country text,
    is_uncredited boolean,
    formats jsonb
);


--
-- Name: title_country; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_country (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    country text NOT NULL
);


--
-- Name: title_credit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_credit (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    category text NOT NULL,
    seq smallint NOT NULL,
    name_id text NOT NULL,
    name_ref text NOT NULL,
    sub_category text,
    credited_as text,
    billing integer,
    roles jsonb,
    attributes jsonb
);


--
-- Name: title_genre; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_genre (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    genre text NOT NULL
);


--
-- Name: title_keyword; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_keyword (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    keyword text NOT NULL,
    category text
);


--
-- Name: title_language; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_language (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    language text NOT NULL
);


--
-- Name: title_production_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_production_status (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    status text NOT NULL,
    status_date date
);


--
-- Name: title_release; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.title_release (
    snapshot_id smallint NOT NULL,
    title_id text NOT NULL,
    seq smallint NOT NULL,
    release_date text NOT NULL,
    release_date_full date,
    country text
);


--
-- Name: altid_pull altid_pull_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.altid_pull
    ADD CONSTRAINT altid_pull_pkey PRIMARY KEY (pull_id);


--
-- Name: live_probe live_probe_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_probe
    ADD CONSTRAINT live_probe_pkey PRIMARY KEY (imdb_id);


--
-- Name: entity_hash pk_entity_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_hash
    ADD CONSTRAINT pk_entity_hash PRIMARY KEY (snapshot_id, kind, entity_id);


--
-- Name: episode_info pk_episode_info; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.episode_info
    ADD CONSTRAINT pk_episode_info PRIMARY KEY (snapshot_id, title_id);


--
-- Name: name pk_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.name
    ADD CONSTRAINT pk_name PRIMARY KEY (snapshot_id, name_id);


--
-- Name: series_info pk_series_info; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.series_info
    ADD CONSTRAINT pk_series_info PRIMARY KEY (snapshot_id, title_id);


--
-- Name: title pk_title; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title
    ADD CONSTRAINT pk_title PRIMARY KEY (snapshot_id, title_id);


--
-- Name: title_aka pk_title_aka; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_aka
    ADD CONSTRAINT pk_title_aka PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_company pk_title_company; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_company
    ADD CONSTRAINT pk_title_company PRIMARY KEY (snapshot_id, title_id, bucket, seq);


--
-- Name: title_country pk_title_country; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_country
    ADD CONSTRAINT pk_title_country PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_credit pk_title_credit; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_credit
    ADD CONSTRAINT pk_title_credit PRIMARY KEY (snapshot_id, title_id, category, seq);


--
-- Name: title_genre pk_title_genre; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_genre
    ADD CONSTRAINT pk_title_genre PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_keyword pk_title_keyword; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_keyword
    ADD CONSTRAINT pk_title_keyword PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_language pk_title_language; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_language
    ADD CONSTRAINT pk_title_language PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_production_status pk_title_production_status; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_production_status
    ADD CONSTRAINT pk_title_production_status PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: title_release pk_title_release; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.title_release
    ADD CONSTRAINT pk_title_release PRIMARY KEY (snapshot_id, title_id, seq);


--
-- Name: public_snapshot public_snapshot_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_snapshot
    ADD CONSTRAINT public_snapshot_label_key UNIQUE (label);


--
-- Name: public_snapshot public_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_snapshot
    ADD CONSTRAINT public_snapshot_pkey PRIMARY KEY (public_snapshot_id);


--
-- Name: snapshot snapshot_label_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_label_key UNIQUE (label);


--
-- Name: snapshot snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshot
    ADD CONSTRAINT snapshot_pkey PRIMARY KEY (snapshot_id);


--
-- Name: ix_backfill_checked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_backfill_checked ON public.backfill_checked USING btree (pull_id, eidr_id);


--
-- Name: ix_class_pull_act; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_class_pull_act ON public.crosswalk_class USING btree (pull_id, action);


--
-- Name: ix_correction_link; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_correction_link ON public.correction USING btree (pull_id, imdb_id, eidr_id, op);


--
-- Name: ix_correction_pull; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_correction_pull ON public.correction USING btree (pull_id, eidr_id);


--
-- Name: ix_correction_rec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_correction_rec ON public.correction USING btree (pull_id, eidr_id, imdb_id, op);


--
-- Name: ix_credit_display; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_display ON public.title_credit USING btree (snapshot_id, title_id) WHERE (name_ref = 'display'::text);


--
-- Name: ix_credit_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_name ON public.title_credit USING btree (snapshot_id, name_id);


--
-- Name: ix_eidr_record_pull; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_eidr_record_pull ON public.eidr_record USING btree (pull_id, eidr_id);


--
-- Name: ix_episode_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_episode_parent ON public.episode_info USING btree (snapshot_id, series_title_id, season_number);


--
-- Name: ix_keyword_value; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_keyword_value ON public.title_keyword USING btree (snapshot_id, keyword);


--
-- Name: ix_link_pull_eidr; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_link_pull_eidr ON public.eidr_imdb_link USING btree (pull_id, eidr_id);


--
-- Name: ix_link_pull_imdb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_link_pull_imdb ON public.eidr_imdb_link USING btree (pull_id, imdb_id);


--
-- Name: ix_name_remapped_to; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_name_remapped_to ON public.name USING btree (remapped_to) WHERE (remapped_to IS NOT NULL);


--
-- Name: ix_reject_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reject_rule ON public.ingest_reject USING btree (snapshot_id, rule);


--
-- Name: ix_shape_pull; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shape_pull ON public.shape_shared USING btree (pull_id, imdb_id);


--
-- Name: ix_title_remapped_to; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_title_remapped_to ON public.title USING btree (remapped_to) WHERE (remapped_to IS NOT NULL);


--
-- Name: ix_title_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_title_type ON public.title USING btree (snapshot_id, title_type);


--
-- Name: ix_title_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_title_year ON public.title USING btree (snapshot_id, year);


--
-- PostgreSQL database dump complete
--

\unrestrict CHh2Vu07rvgIMR3pVYMPAUjuhYqlwWd9dIzMjMBiZapbW6qcpSeH8p2Mh3Lwang
