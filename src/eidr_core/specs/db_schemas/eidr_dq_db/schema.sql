--
-- PostgreSQL database dump
--

\restrict HJg8J4IkDPEVPvZ4zb6vDJgV4Yapmh3kUv3A9pQszBex5oHfICO3pn3fIVjeqmj


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
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: dq_new_key_hash(text, text, text, text, text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.dq_new_key_hash(rule text, content text, scope text, field text, sub text, off text) RETURNS bytea
    LANGUAGE sql IMMUTABLE
    AS $$

  SELECT digest(convert_to(

    rule             || chr(9246) ||

    content          || chr(9246) ||

    scope            || chr(9246) ||

    field            || chr(9246) ||

    coalesce(sub,'') || chr(9246) ||

    coalesce(off,'') || chr(9246) ||

    '',

    'UTF8'), 'sha256');

$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: dq_articles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_articles (
    lang_tag text NOT NULL,
    article_text text NOT NULL,
    article_text_stripped text GENERATED ALWAYS AS (regexp_replace(article_text, '[[:space:][:punct:]]+'::text, ''::text, 'g'::text)) STORED
);


--
-- Name: dq_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_config (
    key text NOT NULL,
    value jsonb NOT NULL
);


--
-- Name: dq_country_freq_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_country_freq_snapshot (
    snapshot_ts timestamp with time zone NOT NULL,
    country_code text NOT NULL,
    occurrences bigint NOT NULL
);


--
-- Name: dq_country_validity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_country_validity (
    id bigint NOT NULL,
    code text NOT NULL,
    name text,
    valid_from_year integer,
    valid_to_year integer,
    CONSTRAINT dq_country_validity_year_bounds_chk CHECK ((((valid_from_year IS NULL) OR ((valid_from_year >= 1800) AND (valid_from_year <= 3000))) AND ((valid_to_year IS NULL) OR ((valid_to_year >= 1800) AND (valid_to_year <= 3000))) AND ((valid_from_year IS NULL) OR (valid_to_year IS NULL) OR (valid_to_year >= valid_from_year))))
);


--
-- Name: dq_country_validity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dq_country_validity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dq_country_validity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dq_country_validity_id_seq OWNED BY public.dq_country_validity.id;


--
-- Name: dq_errors_raw; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_errors_raw (
    run_id bigint NOT NULL,
    rule_code text NOT NULL,
    registrant text,
    content_id text NOT NULL,
    scope text NOT NULL,
    field_name text NOT NULL,
    subfield text,
    offending_value text,
    evidence jsonb,
    error_key_hash bytea NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dq_whitelist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_whitelist (
    id bigint NOT NULL,
    rule_code text NOT NULL,
    content_id text NOT NULL,
    field_name text NOT NULL,
    subfield text,
    error_key_hash bytea NOT NULL,
    reason text,
    whitelisted_by text,
    whitelisted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dq_errors; Type: MATERIALIZED VIEW; Schema: public; Owner: -
--

CREATE MATERIALIZED VIEW public.dq_errors AS
 SELECT r.run_id,
    r.rule_code,
    r.registrant,
    r.content_id,
    r.scope,
    r.field_name,
    r.subfield,
    r.offending_value,
    r.evidence,
    r.error_key_hash,
    r.occurred_at
   FROM (public.dq_errors_raw r
     LEFT JOIN public.dq_whitelist w ON ((w.error_key_hash = r.error_key_hash)))
  WHERE (w.error_key_hash IS NULL)
  WITH NO DATA;


--
-- Name: dq_external_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_external_facts (
    source text NOT NULL,
    external_id text NOT NULL,
    status text NOT NULL,
    facts jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dq_external_facts_source_chk CHECK ((source = ANY (ARRAY['wikidata'::text, 'tmdb_movie'::text, 'tmdb_tv'::text, 'tmdb_episode'::text, 'imdb'::text, 'tmdb_unknown'::text]))),
    CONSTRAINT dq_external_facts_status_chk CHECK ((status = ANY (ARRAY['found'::text, 'not_found'::text, 'error'::text])))
);


--
-- Name: dq_finding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_finding (
    error_key_hash bytea NOT NULL,
    rule_code text NOT NULL,
    content_id text NOT NULL,
    scope text NOT NULL,
    field_name text NOT NULL,
    subfield text,
    offending_value text,
    registrant text,
    first_seen_run bigint NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_run bigint NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    seen_count bigint DEFAULT 1 NOT NULL,
    resolved_run bigint,
    resolved_at timestamp with time zone,
    recurrence_count bigint DEFAULT 0 NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    disposition text,
    disposition_by text,
    disposition_at timestamp with time zone,
    disposition_note text,
    CONSTRAINT dq_finding_status_chk CHECK ((status = ANY (ARRAY['open'::text, 'resolved'::text])))
);


--
-- Name: dq_inclusion_list; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_inclusion_list (
    content_id text NOT NULL
);


--
-- Name: dq_lang_freq_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_lang_freq_snapshot (
    snapshot_ts timestamp with time zone NOT NULL,
    lang_tag text NOT NULL,
    occurrences bigint NOT NULL
);


--
-- Name: dq_registrant_recipients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_registrant_recipients (
    registrant text NOT NULL,
    email text NOT NULL
);


--
-- Name: dq_report_id_map; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_report_id_map (
    run_id bigint NOT NULL,
    seq_no bigint NOT NULL,
    report_id text NOT NULL,
    error_key_hash bytea NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dq_rule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_rule (
    rule_code text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    scope text NOT NULL,
    default_params jsonb NOT NULL,
    enabled_weekly boolean DEFAULT true NOT NULL,
    enabled_monthly boolean DEFAULT true NOT NULL,
    ignore_cutoff_on_monthly boolean DEFAULT false NOT NULL,
    verifiable boolean DEFAULT false NOT NULL,
    severity text DEFAULT 'error'::text NOT NULL,
    weekly_use_closure boolean DEFAULT false NOT NULL,
    CONSTRAINT dq_rule_severity_chk CHECK ((severity = ANY (ARRAY['error'::text, 'review'::text, 'info'::text])))
);


--
-- Name: COLUMN dq_rule.weekly_use_closure; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dq_rule.weekly_use_closure IS 'When true, this rule evaluates against the closure-expanded weekly candidate set (base window records plus their structural neighbors) instead of the base set. Set only for relational rules whose findings can live on a neighbor of a newly created record. Has no effect on monthly runs.';


--
-- Name: dq_verification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_verification (
    run_id bigint NOT NULL,
    error_key_hash bytea NOT NULL,
    rule_code text NOT NULL,
    content_id text NOT NULL,
    verdict text NOT NULL,
    registry_value text,
    detail jsonb NOT NULL,
    verified_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dq_verification_verdict_chk CHECK ((verdict = ANY (ARRAY['corroborated'::text, 'contradicted'::text, 'conflicting'::text, 'no_external_data'::text])))
);


--
-- Name: dq_rule_precision; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.dq_rule_precision AS
 WITH base AS (
         SELECT dq_finding.rule_code,
            count(*) AS total_distinct_findings,
            count(*) FILTER (WHERE (dq_finding.status = 'open'::text)) AS currently_open,
            count(*) FILTER (WHERE (dq_finding.status = 'resolved'::text)) AS resolved_ever,
            count(*) FILTER (WHERE (dq_finding.recurrence_count > 0)) AS recurred_ever,
            avg(dq_finding.seen_count) FILTER (WHERE (dq_finding.status = 'open'::text)) AS avg_runs_open,
            count(*) FILTER (WHERE ((dq_finding.status = 'open'::text) AND (dq_finding.seen_count >= 6))) AS aged_6plus_open
           FROM public.dq_finding
          GROUP BY dq_finding.rule_code
        ), wl AS (
         SELECT fd.rule_code,
            count(*) AS currently_whitelisted
           FROM (public.dq_finding fd
             JOIN public.dq_whitelist w ON ((w.error_key_hash = fd.error_key_hash)))
          GROUP BY fd.rule_code
        ), last_verdict AS (
         SELECT DISTINCT ON (dq_verification.error_key_hash) dq_verification.error_key_hash,
            dq_verification.rule_code,
            dq_verification.verdict
           FROM public.dq_verification
          ORDER BY dq_verification.error_key_hash, dq_verification.run_id DESC
        ), verify_agg AS (
         SELECT last_verdict.rule_code,
            count(*) FILTER (WHERE (last_verdict.verdict = 'corroborated'::text)) AS corroborated,
            count(*) FILTER (WHERE (last_verdict.verdict = 'contradicted'::text)) AS contradicted,
            count(*) FILTER (WHERE (last_verdict.verdict = 'conflicting'::text)) AS conflicting,
            count(*) FILTER (WHERE (last_verdict.verdict = 'no_external_data'::text)) AS no_external_data,
            count(*) AS verified_total
           FROM last_verdict
          GROUP BY last_verdict.rule_code
        )
 SELECT dr.rule_code,
    dr.severity,
    dr.enabled_monthly,
    dr.enabled_weekly,
    dr.verifiable,
    COALESCE(b.total_distinct_findings, (0)::bigint) AS total_distinct_findings,
    COALESCE(b.currently_open, (0)::bigint) AS currently_open,
    COALESCE(b.resolved_ever, (0)::bigint) AS resolved_ever,
    COALESCE(wl.currently_whitelisted, (0)::bigint) AS currently_whitelisted,
    round(((COALESCE(wl.currently_whitelisted, (0)::bigint))::numeric / (NULLIF(b.total_distinct_findings, 0))::numeric), 4) AS whitelist_rate,
    round(((COALESCE(b.resolved_ever, (0)::bigint))::numeric / (NULLIF(b.total_distinct_findings, 0))::numeric), 4) AS resolution_rate,
    round(((COALESCE(b.recurred_ever, (0)::bigint))::numeric / (NULLIF(b.resolved_ever, 0))::numeric), 4) AS recurrence_rate,
    round(b.avg_runs_open, 1) AS avg_runs_open,
    COALESCE(b.aged_6plus_open, (0)::bigint) AS aged_6plus_open,
    v.verified_total,
    v.corroborated,
    v.contradicted,
    v.conflicting,
    v.no_external_data,
    round(((v.corroborated)::numeric / (NULLIF(((v.corroborated + v.contradicted) + v.conflicting), 0))::numeric), 4) AS corroborated_rate,
    round(((v.contradicted)::numeric / (NULLIF(((v.corroborated + v.contradicted) + v.conflicting), 0))::numeric), 4) AS contradicted_rate
   FROM (((public.dq_rule dr
     LEFT JOIN base b ON ((b.rule_code = dr.rule_code)))
     LEFT JOIN wl ON ((wl.rule_code = dr.rule_code)))
     LEFT JOIN verify_agg v ON ((v.rule_code = dr.rule_code)));


--
-- Name: dq_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_run (
    run_id bigint NOT NULL,
    run_type text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    params jsonb NOT NULL
);


--
-- Name: dq_run_rule_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dq_run_rule_stats (
    run_id bigint NOT NULL,
    rule_code text NOT NULL,
    registrant text NOT NULL,
    severity text DEFAULT 'error'::text NOT NULL,
    finding_count bigint NOT NULL
);


--
-- Name: dq_run_run_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dq_run_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dq_run_run_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dq_run_run_id_seq OWNED BY public.dq_run.run_id;


--
-- Name: dq_whitelist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dq_whitelist_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dq_whitelist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dq_whitelist_id_seq OWNED BY public.dq_whitelist.id;


--
-- Name: temp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.temp (
    content_id text NOT NULL
);


--
-- Name: dq_country_validity id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_country_validity ALTER COLUMN id SET DEFAULT nextval('public.dq_country_validity_id_seq'::regclass);


--
-- Name: dq_run run_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_run ALTER COLUMN run_id SET DEFAULT nextval('public.dq_run_run_id_seq'::regclass);


--
-- Name: dq_whitelist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_whitelist ALTER COLUMN id SET DEFAULT nextval('public.dq_whitelist_id_seq'::regclass);


--
-- Name: dq_articles dq_articles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_articles
    ADD CONSTRAINT dq_articles_pkey PRIMARY KEY (lang_tag, article_text);


--
-- Name: dq_config dq_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_config
    ADD CONSTRAINT dq_config_pkey PRIMARY KEY (key);


--
-- Name: dq_country_freq_snapshot dq_country_freq_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_country_freq_snapshot
    ADD CONSTRAINT dq_country_freq_snapshot_pkey PRIMARY KEY (snapshot_ts, country_code);


--
-- Name: dq_country_validity dq_country_validity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_country_validity
    ADD CONSTRAINT dq_country_validity_pkey PRIMARY KEY (id);


--
-- Name: dq_external_facts dq_external_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_external_facts
    ADD CONSTRAINT dq_external_facts_pkey PRIMARY KEY (source, external_id);


--
-- Name: dq_finding dq_finding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_finding
    ADD CONSTRAINT dq_finding_pkey PRIMARY KEY (error_key_hash);


--
-- Name: dq_inclusion_list dq_inclusion_list_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_inclusion_list
    ADD CONSTRAINT dq_inclusion_list_pkey PRIMARY KEY (content_id);


--
-- Name: dq_lang_freq_snapshot dq_lang_freq_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_lang_freq_snapshot
    ADD CONSTRAINT dq_lang_freq_snapshot_pkey PRIMARY KEY (snapshot_ts, lang_tag);


--
-- Name: dq_registrant_recipients dq_registrant_recipients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_registrant_recipients
    ADD CONSTRAINT dq_registrant_recipients_pkey PRIMARY KEY (registrant, email);


--
-- Name: dq_report_id_map dq_report_id_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_report_id_map
    ADD CONSTRAINT dq_report_id_map_pkey PRIMARY KEY (run_id, seq_no);


--
-- Name: dq_report_id_map dq_report_id_map_run_id_report_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_report_id_map
    ADD CONSTRAINT dq_report_id_map_run_id_report_id_key UNIQUE (run_id, report_id);


--
-- Name: dq_rule dq_rule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_rule
    ADD CONSTRAINT dq_rule_pkey PRIMARY KEY (rule_code);


--
-- Name: dq_run dq_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_run
    ADD CONSTRAINT dq_run_pkey PRIMARY KEY (run_id);


--
-- Name: dq_run_rule_stats dq_run_rule_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_run_rule_stats
    ADD CONSTRAINT dq_run_rule_stats_pkey PRIMARY KEY (run_id, rule_code, registrant);


--
-- Name: dq_verification dq_verification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_verification
    ADD CONSTRAINT dq_verification_pkey PRIMARY KEY (run_id, error_key_hash);


--
-- Name: dq_whitelist dq_whitelist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_whitelist
    ADD CONSTRAINT dq_whitelist_pkey PRIMARY KEY (id);


--
-- Name: temp temp_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.temp
    ADD CONSTRAINT temp_pkey PRIMARY KEY (content_id);


--
-- Name: dq_country_validity_code_from_to_uq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX dq_country_validity_code_from_to_uq ON public.dq_country_validity USING btree (code, COALESCE(valid_from_year, '-2147483648'::integer), COALESCE(valid_to_year, 2147483647));


--
-- Name: dq_country_validity_code_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_country_validity_code_idx ON public.dq_country_validity USING btree (code);


--
-- Name: dq_errors_raw_cid_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_cid_idx ON public.dq_errors_raw USING btree (content_id);


--
-- Name: dq_errors_raw_hash_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_hash_idx ON public.dq_errors_raw USING btree (error_key_hash);


--
-- Name: dq_errors_raw_rule_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_rule_idx ON public.dq_errors_raw USING btree (rule_code);


--
-- Name: dq_errors_raw_run_id_registrant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_run_id_registrant_idx ON public.dq_errors_raw USING btree (run_id, registrant);


--
-- Name: dq_errors_raw_run_id_rule_code_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_run_id_rule_code_idx ON public.dq_errors_raw USING btree (run_id, rule_code);


--
-- Name: dq_errors_raw_run_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_errors_raw_run_idx ON public.dq_errors_raw USING btree (run_id);


--
-- Name: dq_external_facts_fetched_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_external_facts_fetched_idx ON public.dq_external_facts USING btree (fetched_at);


--
-- Name: dq_finding_content_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_content_idx ON public.dq_finding USING btree (content_id);


--
-- Name: dq_finding_first_seen_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_first_seen_idx ON public.dq_finding USING btree (first_seen_run);


--
-- Name: dq_finding_last_seen_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_last_seen_idx ON public.dq_finding USING btree (last_seen_run);


--
-- Name: dq_finding_registrant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_registrant_idx ON public.dq_finding USING btree (registrant);


--
-- Name: dq_finding_rule_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_rule_idx ON public.dq_finding USING btree (rule_code);


--
-- Name: dq_finding_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_finding_status_idx ON public.dq_finding USING btree (status);


--
-- Name: dq_run_rule_stats_registrant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_run_rule_stats_registrant_idx ON public.dq_run_rule_stats USING btree (registrant);


--
-- Name: dq_run_rule_stats_rule_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_run_rule_stats_rule_idx ON public.dq_run_rule_stats USING btree (rule_code);


--
-- Name: dq_verification_content_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_verification_content_idx ON public.dq_verification USING btree (content_id);


--
-- Name: dq_verification_rule_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_verification_rule_idx ON public.dq_verification USING btree (rule_code);


--
-- Name: dq_verification_run_verdict_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX dq_verification_run_verdict_idx ON public.dq_verification USING btree (run_id, verdict);


--
-- Name: idx_dq_errors_error_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dq_errors_error_hash ON public.dq_errors USING btree (error_key_hash);


--
-- Name: idx_dq_inclusion_list_content; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dq_inclusion_list_content ON public.dq_inclusion_list USING btree (content_id);


--
-- Name: idx_dq_report_id_map_run_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dq_report_id_map_run_hash ON public.dq_report_id_map USING btree (run_id, error_key_hash);


--
-- Name: uq_dq_errors_run_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_dq_errors_run_hash ON public.dq_errors_raw USING btree (run_id, error_key_hash);


--
-- Name: uq_dq_whitelist_error_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_dq_whitelist_error_hash ON public.dq_whitelist USING btree (error_key_hash);


--
-- Name: dq_errors_raw dq_errors_raw_rule_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_errors_raw
    ADD CONSTRAINT dq_errors_raw_rule_code_fkey FOREIGN KEY (rule_code) REFERENCES public.dq_rule(rule_code);


--
-- Name: dq_errors_raw dq_errors_raw_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_errors_raw
    ADD CONSTRAINT dq_errors_raw_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.dq_run(run_id) ON DELETE CASCADE;


--
-- Name: dq_report_id_map dq_report_id_map_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_report_id_map
    ADD CONSTRAINT dq_report_id_map_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.dq_run(run_id) ON DELETE CASCADE;


--
-- Name: dq_run_rule_stats dq_run_rule_stats_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_run_rule_stats
    ADD CONSTRAINT dq_run_rule_stats_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.dq_run(run_id) ON DELETE CASCADE;


--
-- Name: dq_verification dq_verification_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dq_verification
    ADD CONSTRAINT dq_verification_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.dq_run(run_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict HJg8J4IkDPEVPvZ4zb6vDJgV4Yapmh3kUv3A9pQszBex5oHfICO3pn3fIVjeqmj
