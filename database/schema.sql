-- Generated from database/models.py. Original snapshots use a separate archived schema.

CREATE TABLE archive_imports (
	source_sha256 VARCHAR(64) NOT NULL, 
	source_name VARCHAR(100) NOT NULL, 
	imported_at VARCHAR(40) NOT NULL, 
	table_counts JSON NOT NULL, 
	PRIMARY KEY (source_sha256)
);

CREATE TABLE devices (
	device_id VARCHAR(48) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	last_seen VARCHAR(40), 
	controller JSON NOT NULL, 
	active_boot VARCHAR(64), 
	retired_boots JSON NOT NULL, 
	PRIMARY KEY (device_id)
);

CREATE TABLE warehouses (
	warehouse_id VARCHAR(48) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	available BOOLEAN NOT NULL, 
	capacity FLOAT NOT NULL, 
	minimum_temperature FLOAT NOT NULL, 
	maximum_temperature FLOAT NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	PRIMARY KEY (warehouse_id)
);

CREATE TABLE archive_records (
	id INTEGER NOT NULL, 
	source_sha256 VARCHAR(64) NOT NULL, 
	table_name VARCHAR(40) NOT NULL, 
	source_key VARCHAR(100) NOT NULL, 
	device_id VARCHAR(100), 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source_sha256, table_name, source_key), 
	FOREIGN KEY(source_sha256) REFERENCES archive_imports (source_sha256)
);

CREATE INDEX ix_archive_records_device_id ON archive_records (device_id);

CREATE INDEX ix_archive_records_source_sha256 ON archive_records (source_sha256);

CREATE INDEX ix_archive_records_table_name ON archive_records (table_name);

CREATE TABLE fault_events (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_fault_events_device_id ON fault_events (device_id);

CREATE TABLE rerouting_events (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_rerouting_events_device_id ON rerouting_events (device_id);

CREATE TABLE self_healing_events (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_self_healing_events_device_id ON self_healing_events (device_id);

CREATE TABLE system_health (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_system_health_device_id ON system_health (device_id);

CREATE TABLE telemetry (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	boot_id VARCHAR(64) NOT NULL, 
	sequence INTEGER NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	received_at VARCHAR(40) NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	payload JSON NOT NULL, 
	decision JSON NOT NULL, 
	archived BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (device_id, boot_id, sequence), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_telemetry_device_id ON telemetry (device_id);

CREATE INDEX ix_telemetry_timestamp ON telemetry (timestamp);

CREATE TABLE test_results (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_test_results_device_id ON test_results (device_id);

CREATE TABLE control_commands (
	id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	boot_id VARCHAR(64) NOT NULL, 
	based_on_sequence INTEGER NOT NULL, 
	command_type VARCHAR(40) NOT NULL, 
	primary_cooling BOOLEAN NOT NULL, 
	backup_cooling BOOLEAN NOT NULL, 
	reason TEXT NOT NULL, 
	triggered_by_fault INTEGER, 
	status VARCHAR(24) NOT NULL, 
	created_at VARCHAR(40) NOT NULL, 
	expires_at VARCHAR(40) NOT NULL, 
	acknowledged_at VARCHAR(40), 
	confirmed_at VARCHAR(40), 
	acknowledgement JSON, 
	PRIMARY KEY (id), 
	CONSTRAINT cooling_interlock CHECK (NOT (primary_cooling AND backup_cooling)), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id), 
	FOREIGN KEY(triggered_by_fault) REFERENCES fault_events (id)
);

CREATE INDEX ix_control_commands_device_id ON control_commands (device_id);

CREATE INDEX ix_control_commands_status ON control_commands (status);

CREATE TABLE predictions (
	id INTEGER NOT NULL, 
	telemetry_id INTEGER NOT NULL, 
	device_id VARCHAR(48) NOT NULL, 
	timestamp VARCHAR(40) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (telemetry_id), 
	FOREIGN KEY(telemetry_id) REFERENCES telemetry (id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_predictions_device_id ON predictions (device_id);
