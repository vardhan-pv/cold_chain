"""Train future measured logs with reviewed labels and chronological boot holdouts.

This importer does not create measurements or certify their provenance. No
measured model is bundled; this path is exercised only with software fixtures.
"""
import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal
import pandas as pd
from pydantic import Field, StrictInt
from backend.schemas import Contract, Telemetry
from ml.feature_engineering import features_for
from ml.train import fit_dataset

class LabelledReading(Contract):
    split: Literal['train','validation','test']
    label: StrictInt = Field(ge=0, le=1)
    evidence: str = Field(min_length=16, max_length=1000)
    telemetry: Telemetry

def prepare(path):
    path=Path(path)
    records=[LabelledReading.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    if not records:
        raise ValueError('No labelled readings provided')
    groups={};identities=set();split_times={k:[] for k in ('train','validation','test')}
    for record in records:
        t=record.telemetry
        if t.mode!='HARDWARE':
            raise ValueError('Measured training rejects SIMULATION readings; use ml.train for simulation')
        group=(t.device_id,t.boot_id)
        identity=(*group,t.sequence)
        if identity in identities:
            raise ValueError('Duplicate device/boot/sequence in labelled readings')
        identities.add(identity)
        if group in groups and groups[group][0].split!=record.split:
            raise ValueError('The same boot cannot cross train/validation/test splits')
        groups.setdefault(group,[]).append(record)
        split_times[record.split].append(t.timestamp.timestamp())
    if not all(split_times.values()):
        raise ValueError('Training, validation and test runs are all required')
    if max(split_times['train'])>=min(split_times['validation']) or max(split_times['validation'])>=min(split_times['test']):
        raise ValueError('Use chronological held-out runs: training before validation before testing')
    rows=[]
    for group,episode in groups.items():
        history=[]
        for record in sorted(episode,key=lambda r:r.telemetry.timestamp):
            t=record.telemetry
            if history and (t.timestamp<=history[-1].timestamp or t.sequence<=history[-1].sequence):
                raise ValueError('Each boot needs strictly increasing sample times and sequences')
            history=[p for p in history if (t.timestamp-p.timestamp).total_seconds()<=60]
            history.append(t)
            features=features_for(history)
            if features is not None:
                rows.append({**features,'episode_id':'/'.join(group),'split':record.split,
                    'label':record.label,'provenance':'MEASURED_DATA','evidence':record.evidence})
    if not rows:
        raise ValueError('No valid sensor rows available for features')
    return pd.DataFrame(rows), {'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'input_readings':len(records),'usable_readings':len(rows),'excluded_invalid_sensor_rows':len(records)-len(rows),
        'verification':'OPERATOR_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labelled_jsonl',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='Use a separate directory to retain the demo model')
    args=parser.parse_args()
    frame,evidence=prepare(args.labelled_jsonl)
    fit_dataset(frame,args.output,provenance='MEASURED_DATA',evidence=evidence)

if __name__=='__main__':main()
