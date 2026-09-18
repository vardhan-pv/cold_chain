from xgboost import XGBClassifier

def train(X, y):
    model = XGBClassifier(n_estimators=90, max_depth=3, learning_rate=.08,
        subsample=.85, colsample_bytree=.9, reg_lambda=2.0, random_state=42,
        tree_method='hist', n_jobs=2, eval_metric='logloss')
    return model.fit(X, y)
