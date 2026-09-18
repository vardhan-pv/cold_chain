from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

def metrics(y, probability, threshold=.5):
    pred = probability >= threshold
    return {'accuracy': float(accuracy_score(y,pred)),
        'precision': float(precision_score(y,pred,zero_division=0)),
        'recall': float(recall_score(y,pred,zero_division=0)),
        'f1': float(f1_score(y,pred,zero_division=0)),
        'roc_auc': float(roc_auc_score(y,probability)) if len(set(y)) == 2 else None,
        'confusion_matrix': confusion_matrix(y,pred,labels=[0,1]).tolist(),
        'samples': int(len(y)), 'positive_samples': int(sum(y))}
