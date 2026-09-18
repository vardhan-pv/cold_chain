from sklearn.ensemble import RandomForestClassifier

def train(X, y):
    model = RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=4,
        class_weight='balanced', random_state=42, n_jobs=2)
    return model.fit(X, y)
