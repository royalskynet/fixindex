#!/usr/bin/env python3
"""Short stored tokens must not produce prefix-fuzzy search hits."""
from fxsearch import BM25Engine, tokenize


def test():
    for word in ('t', 'ty'):
        engine = BM25Engine([{'tokens': [word]}])
        assert engine.search('TypeError') == [], word
        assert engine.coverage(0, {'typeerror'}) == 0.0, word
        assert engine.search(word), word
        assert engine.score(0, {word}) == engine.idf(word), word
        assert engine.coverage(0, {word}) == 1.0, word

    for stored, query in (('typ', 'TypeError'), ('typeerror', 'typ')):
        engine = BM25Engine([{'tokens': [stored]}])
        assert engine.search(query), (stored, query)
        assert engine.coverage(0, {query.lower()}) == 1.0, (stored, query)

    engine = BM25Engine([{'tokens': tokenize("can't connect")}])
    assert engine.search('TypeError') == []
    assert engine.coverage(0, {'typeerror'}) == 0.0
    assert engine.search('') == []
    assert engine.coverage(0, set()) == 0.0
    assert BM25Engine([]).search('TypeError') == []
    print('PASS test_search_prefix_min_len')


if __name__ == '__main__':
    test()
