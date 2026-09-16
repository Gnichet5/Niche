import unittest
from janus.memory_graph import build_graph

class GraphTests(unittest.TestCase):
    def test_real_similarity_and_no_text_export(self):
        class Collection:
            def count(self): return 3
            def get(self, **kwargs):
                self.kwargs=kwargs
                return {'ids':['a','b','c'], 'embeddings':[[1,0],[.99,.01],[0,1]]}
        c=Collection(); graph=build_graph(c)
        self.assertEqual(graph['edges'], [{'source':'a','target':'b','weight':1}])
        self.assertEqual(c.kwargs['include'], ['embeddings'])
        self.assertEqual(graph['nodes'][0], {'id':'a'})

    def test_bound_and_empty_vectors(self):
        class Collection:
            def count(self): return 1000
            def get(self, **kwargs):
                self.kwargs=kwargs
                return {'ids':['a'], 'embeddings':None}
        c=Collection(); graph=build_graph(c,10000)
        self.assertEqual(c.kwargs['limit'],96)
        self.assertEqual(c.kwargs['offset'],904)
        self.assertEqual(graph['edges'],[])

if __name__ == '__main__': unittest.main()
