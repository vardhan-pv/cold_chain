import hashlib, json, time
from pathlib import Path
import joblib
import pandas as pd
from xgboost import XGBClassifier
from ml.feature_engineering import FEATURES, FEATURE_VERSION

class Predictor:
    def __init__(self, directory=None):
        self.directory=Path(directory or Path(__file__).parent/'trained_models')
        self.ready=False
        self.error=None
        self.manifest={}
        try:
            self.manifest=json.loads((self.directory/'manifest.json').read_text())
            if self.manifest['features'] != FEATURES or self.manifest['feature_version'] != FEATURE_VERSION:
                raise ValueError('Feature schema mismatch')
            for filename,digest in self.manifest['artifact_sha256'].items():
                if hashlib.sha256((self.directory/filename).read_bytes()).hexdigest() != digest:
                    raise ValueError('Artifact checksum mismatch')
            self.xgb=XGBClassifier();self.xgb.load_model(self.directory/'xgboost_model.json')
            # Only load the locally built trusted artifact, never a user-uploaded pickle.
            self.rf=joblib.load(self.directory/'random_forest_model.joblib')
            self.rf.n_jobs=1
            self.ready=True
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.error=str(exc)

    def predict(self, features):
        if not self.ready or features is None:
            return {'status':'MODEL_UNAVAILABLE' if not self.ready else 'INVALID_SENSOR_DATA',
                'xgboost_probability':None,'random_forest_probability':None,
                'ensemble_probability':None,'inference_ms':None,'model_version':None,
                'training_provenance':self.manifest.get('training_provenance')}
        if list(features) != FEATURES:
            raise ValueError('Feature order mismatch')
        started=time.perf_counter()
        X=pd.DataFrame([[features[k] for k in FEATURES]],columns=FEATURES)
        a=float(self.xgb.predict_proba(X)[0,1]);b=float(self.rf.predict_proba(X)[0,1])
        w=self.manifest['xgboost_weight'];p=w*a+(1-w)*b
        return {'status':'INFERENCE_COMPLETE','xgboost_probability':a,'random_forest_probability':b,
            'ensemble_probability':p,'predicted_anomaly':p>=self.manifest['threshold'],
            'threshold':self.manifest['threshold'],'model_version':self.manifest['model_version'],
            'training_provenance':self.manifest['training_provenance'],
            'hardware_validated':False,'inference_ms':round((time.perf_counter()-started)*1000,3)}
