-- Run this in the Supabase SQL editor after creating the project.
-- Enables PostGIS and sets up the core tables.

create extension if not exists postgis;

-- Grid cells covering the monitored forest area
create table if not exists grid_cells (
    cell_id text primary key,
    center_lat double precision not null,
    center_lng double precision not null,
    min_lat double precision not null,
    min_lng double precision not null,
    max_lat double precision not null,
    max_lng double precision not null,
    geom geometry(Polygon, 4326),
    created_at timestamptz default now()
);

create index if not exists grid_cells_geom_idx on grid_cells using gist (geom);

-- Detection events (source-agnostic: satellite, drone, webcam, aerial)
create table if not exists detections (
    id uuid primary key default gen_random_uuid(),
    cell_id text references grid_cells(cell_id),
    source text not null,
    fire_detected boolean not null,
    smoke_detected boolean not null,
    confidence double precision not null,
    bbox double precision[],
    detected_at timestamptz default now()
);

create index if not exists detections_cell_id_idx on detections (cell_id);

-- Migration for existing projects: adds review status to detections. Safe to
-- re-run; apply this statement in the Supabase SQL editor before using the
-- status filter/control in the API. Allowed values are enforced by the check.
alter table detections
    add column if not exists status text not null default 'unverified';

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'detections_status_allowed'
          and conrelid = 'detections'::regclass
    ) then
        alter table detections
            add constraint detections_status_allowed
            check (status in ('unverified', 'confirmed', 'false_positive', 'resolved'));
    end if;
end $$;

-- Risk predictions from the weather-based ML model
create table if not exists risk_predictions (
    id uuid primary key default gen_random_uuid(),
    cell_id text references grid_cells(cell_id),
    risk_score double precision not null,
    risk_level text not null,
    features_used jsonb not null,
    predicted_at timestamptz default now()
);

create index if not exists risk_predictions_cell_id_idx on risk_predictions (cell_id);

-- Latest daily moisture codes plus the prior-day baseline used for same-day
-- recalculation. One row per cell; run this schema update before using FWI.
create table if not exists fwi_state (
    cell_id text primary key references grid_cells(cell_id),
    ffmc double precision not null default 85,
    dmc double precision not null default 6,
    dc double precision not null default 15,
    previous_ffmc double precision not null default 85,
    previous_dmc double precision not null default 6,
    previous_dc double precision not null default 15,
    calculation_date date not null,
    updated_at timestamptz default now()
);

-- Alerts generated from detections or risk thresholds
create table if not exists alerts (
    id uuid primary key default gen_random_uuid(),
    cell_id text references grid_cells(cell_id),
    alert_type text not null,
    message text not null,
    severity text not null,
    created_at timestamptz default now()
);

create index if not exists alerts_cell_id_idx on alerts (cell_id);
create index if not exists alerts_created_at_idx on alerts (created_at desc);
