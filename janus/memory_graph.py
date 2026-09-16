"""Bounded local graph from stored embeddings; never generates embeddings."""
import math


def build_graph(collection, limit=96):
    limit = max(1, min(limit, 96))
    total = collection.count()
    data = collection.get(limit=limit, offset=max(0, total - limit), include=['embeddings'])
    ids = data['ids']
    raw = data.get('embeddings')
    vectors = []
    for row in ([] if raw is None else raw):
        values = [float(v) for v in row]
        norm = math.sqrt(sum(v*v for v in values))
        vectors.append([v/norm for v in values] if norm and math.isfinite(norm) else [])
    edges = {}
    for i, vector in enumerate(vectors):
        if not vector:
            continue
        neighbors = []
        for j, other in enumerate(vectors):
            if i == j or len(vector) != len(other):
                continue
            score = sum(a*b for a, b in zip(vector, other))
            if score >= 0.65:
                neighbors.append((score, j))
        for score, j in sorted(neighbors, reverse=True)[:2]:
            edges[tuple(sorted((i, j)))] = round(min(1, score), 3)
    return {'nodes': [{'id': key} for key in ids],
            'edges': [{'source': ids[i], 'target': ids[j], 'weight': score}
                      for (i, j), score in edges.items()], 'total': total}
