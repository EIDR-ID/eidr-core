--
-- PostgreSQL database dump
--

\restrict cZDMHicf7Porr87u3X92eAXldX4bAcZ26Zs41QXsJLa9FcLFOUnn1Eg7dwAHPam


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
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: _set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public._set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: code_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_mapping (
    language_code text NOT NULL,
    scheme text NOT NULL,
    code text NOT NULL,
    source text DEFAULT 'legacy'::text NOT NULL
);


--
-- Name: language; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.language (
    code text NOT NULL,
    group_tag text NOT NULL,
    deprecated boolean DEFAULT false NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    source text DEFAULT 'legacy'::text NOT NULL,
    preferred_value text
);


--
-- Name: COLUMN language.preferred_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.language.preferred_value IS 'Replacement code for deprecated language tags (BCP-47/registry "preferred-value"). NULL if none.';


--
-- Name: language_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.language_group (
    group_tag text NOT NULL,
    group_name text NOT NULL,
    source text DEFAULT 'legacy'::text NOT NULL
);


--
-- Name: language_mode; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.language_mode (
    language_code text NOT NULL,
    mode text NOT NULL,
    source text DEFAULT 'legacy'::text NOT NULL,
    CONSTRAINT language_mode_mode_check CHECK ((mode = ANY (ARRAY['audio'::text, 'visual'::text])))
);


--
-- Name: language_name; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.language_name (
    language_code text NOT NULL,
    name_lang text NOT NULL,
    name_type text NOT NULL,
    alt_type text DEFAULT ''::text NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    name text NOT NULL,
    source text DEFAULT 'legacy'::text NOT NULL
);


--
-- Name: scheme_info; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheme_info (
    scheme text NOT NULL,
    source text DEFAULT ''::text NOT NULL,
    version text DEFAULT ''::text NOT NULL,
    copyright text DEFAULT ''::text NOT NULL,
    license text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    maintainer text,
    source_url text,
    retrieved_at timestamp with time zone,
    license_file text,
    notes text
);


--
-- Name: TABLE scheme_info; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.scheme_info IS 'Attribution metadata for external language code schemes. Mirrors the SCHEME_INFO dict in main.py; the in-process dict remains the authoritative source until this table is fully populated.';


--
-- Name: COLUMN scheme_info.maintainer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheme_info.maintainer IS 'Registration authority or maintaining organization (moved out of license).';


--
-- Name: COLUMN scheme_info.source_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheme_info.source_url IS 'Canonical URL of the source data used for the mapping.';


--
-- Name: COLUMN scheme_info.retrieved_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheme_info.retrieved_at IS 'When the mapped data was retrieved from the source.';


--
-- Name: COLUMN scheme_info.license_file; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheme_info.license_file IS 'Relative path to the license/notice file in the docs folder, served on request.';


--
-- Name: COLUMN scheme_info.notes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheme_info.notes IS 'Provenance and usage notes (e.g., scope limits, governance status).';


--
-- Name: temp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.temp (
    language_code text NOT NULL,
    language_name text NOT NULL,
    group_code text NOT NULL,
    group_name text NOT NULL,
    rule_no text NOT NULL,
    "ISO Language Code	Language Name" character varying(75)
);


--
-- Name: code_mapping code_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_mapping
    ADD CONSTRAINT code_mapping_pkey PRIMARY KEY (language_code, scheme, code);


--
-- Name: language_group language_group_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_group
    ADD CONSTRAINT language_group_pkey1 PRIMARY KEY (group_tag);


--
-- Name: language_mode language_mode_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_mode
    ADD CONSTRAINT language_mode_pkey PRIMARY KEY (language_code, mode);


--
-- Name: language_name language_name_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_name
    ADD CONSTRAINT language_name_pkey1 PRIMARY KEY (language_code, name_lang, name_type, alt_type, order_index);


--
-- Name: language language_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language
    ADD CONSTRAINT language_pkey1 PRIMARY KEY (code);


--
-- Name: scheme_info scheme_info_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheme_info
    ADD CONSTRAINT scheme_info_pkey PRIMARY KEY (scheme);


--
-- Name: language_name uq_language_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_name
    ADD CONSTRAINT uq_language_name_key UNIQUE (language_code, name_lang, name_type, alt_type, order_index);


--
-- Name: idx_code_mapping_code_scheme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_mapping_code_scheme ON public.code_mapping USING btree (lower(language_code), lower(scheme));


--
-- Name: idx_code_mapping_scheme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_mapping_scheme ON public.code_mapping USING btree (scheme);


--
-- Name: idx_code_mapping_scheme_code_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_code_mapping_scheme_code_lower ON public.code_mapping USING btree (lower(scheme), lower(code));


--
-- Name: idx_language_code_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_code_lower ON public.language USING btree (lower(code));


--
-- Name: idx_language_deprecated_missing_preferred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_deprecated_missing_preferred ON public.language USING btree (code) WHERE ((deprecated IS TRUE) AND ((preferred_value IS NULL) OR (preferred_value = ''::text)));


--
-- Name: idx_language_group_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_group_tag ON public.language USING btree (group_tag);


--
-- Name: idx_language_mode_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_mode_code ON public.language_mode USING btree (lower(language_code));


--
-- Name: idx_language_name_code_lang_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_name_code_lang_type ON public.language_name USING btree (language_code, name_lang, name_type, alt_type, order_index);


--
-- Name: idx_language_name_lang_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_name_lang_type ON public.language_name USING btree (name_lang, name_type);


--
-- Name: idx_language_name_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_name_name ON public.language_name USING gin (name public.gin_trgm_ops);


--
-- Name: idx_language_name_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_name_name_trgm ON public.language_name USING gin (name public.gin_trgm_ops);


--
-- Name: idx_language_preferred_value; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_preferred_value ON public.language USING btree (preferred_value);


--
-- Name: idx_language_status_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_language_status_group ON public.language USING btree (status, group_tag);


--
-- Name: scheme_info trg_scheme_info_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_scheme_info_updated_at BEFORE UPDATE ON public.scheme_info FOR EACH ROW EXECUTE FUNCTION public._set_updated_at();


--
-- Name: code_mapping code_mapping_language_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_mapping
    ADD CONSTRAINT code_mapping_language_code_fkey FOREIGN KEY (language_code) REFERENCES public.language(code) ON DELETE CASCADE;


--
-- Name: language language_group_tag_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language
    ADD CONSTRAINT language_group_tag_fkey FOREIGN KEY (group_tag) REFERENCES public.language_group(group_tag);


--
-- Name: language_mode language_mode_language_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_mode
    ADD CONSTRAINT language_mode_language_code_fkey FOREIGN KEY (language_code) REFERENCES public.language(code) ON DELETE CASCADE;


--
-- Name: language_name language_name_language_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.language_name
    ADD CONSTRAINT language_name_language_code_fkey FOREIGN KEY (language_code) REFERENCES public.language(code) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict cZDMHicf7Porr87u3X92eAXldX4bAcZ26Zs41QXsJLa9FcLFOUnn1Eg7dwAHPam
