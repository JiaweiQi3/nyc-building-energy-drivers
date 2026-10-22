-- Build the building_energy MySQL database from data/nyc_ll84_cleaned.csv.
--
-- Run from the repository root with local file loading enabled:
--   mysql --local-infile=1 -u <user> -p < analysis/build_database.sql
--
-- The extract holds one row per benchmarking record; a building can appear in
-- several records. Building holds the identity of each building, and every
-- measurement table is keyed by record_id, so the analysis keeps all records.

CREATE DATABASE IF NOT EXISTS building_energy;
USE building_energy;

DROP TABLE IF EXISTS Energy_Usage_Intensity;
DROP TABLE IF EXISTS Total_Energy_Use;
DROP TABLE IF EXISTS Electricity_Use;
DROP TABLE IF EXISTS Gross_Floor_Area;
DROP TABLE IF EXISTS Housing_Age;
DROP TABLE IF EXISTS Benchmark_Record;
DROP TABLE IF EXISTS Building;
DROP TABLE IF EXISTS NYC_Median_EUI_By_Type;
DROP TABLE IF EXISTS staging_records;

-- 1. Staging table with the CSV columns in order
CREATE TABLE staging_records (
    record_id INT AUTO_INCREMENT PRIMARY KEY,
    building_id BIGINT,
    name TEXT,
    bbl TEXT,
    nyc_bin TEXT,
    address TEXT,
    city TEXT,
    zipcode TEXT,
    building_type_id VARCHAR(50),
    building_type TEXT,
    year_built INT,
    energy_star_score INT,
    national_median_energy_star INT,
    weather_normalized_site_energy DOUBLE,
    weather_normalized_site_eui DOUBLE,
    national_median_site_eui DOUBLE,
    electricity_grid_purchase DOUBLE,
    property_use_types TEXT,
    largest_use_type TEXT,
    largest_use_gfa DOUBLE,
    second_use_type TEXT,
    second_use_gfa DOUBLE,
    third_use_type TEXT,
    third_use_gfa DOUBLE,
    total_gfa DOUBLE
);

LOAD DATA LOCAL INFILE 'data/nyc_ll84_cleaned.csv'
INTO TABLE staging_records
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(building_id, name, bbl, nyc_bin, address, city, zipcode, building_type_id, building_type,
 year_built, energy_star_score, national_median_energy_star, weather_normalized_site_energy,
 weather_normalized_site_eui, national_median_site_eui, electricity_grid_purchase,
 property_use_types, largest_use_type, largest_use_gfa, second_use_type, second_use_gfa,
 third_use_type, third_use_gfa, total_gfa);

-- 2. Normalized tables
CREATE TABLE Building (
    building_id BIGINT PRIMARY KEY,
    name TEXT,
    address TEXT,
    nyc_bin TEXT,
    city VARCHAR(100),
    zipcode VARCHAR(20)
);

CREATE TABLE Benchmark_Record (
    record_id INT PRIMARY KEY,
    building_id BIGINT NOT NULL,
    building_type_id VARCHAR(50),
    largest_use_type VARCHAR(100),
    FOREIGN KEY (building_id) REFERENCES Building(building_id)
);

CREATE TABLE Housing_Age (
    record_id INT PRIMARY KEY,
    year_built INT,
    FOREIGN KEY (record_id) REFERENCES Benchmark_Record(record_id)
);

CREATE TABLE Gross_Floor_Area (
    record_id INT PRIMARY KEY,
    total_gfa DOUBLE,
    FOREIGN KEY (record_id) REFERENCES Benchmark_Record(record_id)
);

CREATE TABLE Electricity_Use (
    record_id INT PRIMARY KEY,
    electricity_use DOUBLE,
    FOREIGN KEY (record_id) REFERENCES Benchmark_Record(record_id)
);

CREATE TABLE Total_Energy_Use (
    record_id INT PRIMARY KEY,
    total_energy_use DOUBLE,
    FOREIGN KEY (record_id) REFERENCES Benchmark_Record(record_id)
);

CREATE TABLE Energy_Usage_Intensity (
    record_id INT PRIMARY KEY,
    site_eui DOUBLE,
    FOREIGN KEY (record_id) REFERENCES Benchmark_Record(record_id)
);

CREATE TABLE NYC_Median_EUI_By_Type (
    building_type_id VARCHAR(50) PRIMARY KEY,
    building_type TEXT,
    national_median_site_eui DOUBLE
);

-- 3. Fill them from staging
INSERT INTO Building (building_id, name, address, nyc_bin, city, zipcode)
SELECT building_id, ANY_VALUE(name), ANY_VALUE(address), ANY_VALUE(nyc_bin),
       ANY_VALUE(city), ANY_VALUE(zipcode)
FROM staging_records
GROUP BY building_id;

INSERT INTO Benchmark_Record (record_id, building_id, building_type_id, largest_use_type)
SELECT record_id, building_id, building_type_id, largest_use_type FROM staging_records;

INSERT INTO Housing_Age SELECT record_id, year_built FROM staging_records;
INSERT INTO Gross_Floor_Area SELECT record_id, total_gfa FROM staging_records;
INSERT INTO Electricity_Use SELECT record_id, electricity_grid_purchase FROM staging_records;
INSERT INTO Total_Energy_Use SELECT record_id, weather_normalized_site_energy FROM staging_records;
INSERT INTO Energy_Usage_Intensity SELECT record_id, weather_normalized_site_eui FROM staging_records;

INSERT INTO NYC_Median_EUI_By_Type (building_type_id, building_type, national_median_site_eui)
SELECT building_type_id, ANY_VALUE(building_type), ANY_VALUE(national_median_site_eui)
FROM staging_records
WHERE building_type_id IS NOT NULL
GROUP BY building_type_id;

DROP TABLE staging_records;
