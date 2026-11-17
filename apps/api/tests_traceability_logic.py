"""FR17d drift and FR17e naming logic (core/traceability.py). No database, AI or Kroki needed.
Run: PYTHONPATH=. python tests_traceability_logic.py"""
from core.traceability import drift_warnings, mentions, naming_issues, rename_in_diagram, shape


def el(eid, label, kind='use_case', item=None, refs=(), assumption=False):
    return {'element_id': eid, 'model_item_id': item, 'kind': kind, 'label': label,
            'statement_ids': list(refs), 'is_assumption': assumption}


STATEMENTS = {
    'st_1': {'ref': 'R-001', 'text': 'The librarian issues a book to a member.'},
    'st_2': {'ref': 'R-002', 'text': 'A member can return books and pay fines.'},
}
ROOT = {'elements': [
    el('it_lib', 'Librarian', 'actor', 'it_lib', ['st_1']), el('uc_issue', 'Issue book', 'use_case', None, ['st_1']),
    el('it_mem', 'Member', 'actor', 'it_mem', ['st_2']), el('uc_return', 'Return book', 'use_case', None, ['st_2']),
    el('uc_login', 'Log in', 'use_case', None, [], True)]}
ROOT_LINES = [('it_lib-uc_issue', 'association', 'it_lib', 'uc_issue', None),
              ('it_mem-uc_return', 'association', 'it_mem', 'uc_return', None)]


def check_mentions():
    assert mentions('The librarian issues a book to a member.', 'Issue book')  # endings do not matter
    assert mentions('The librarian issues a book to a member.', 'Librarian')
    assert not mentions('The librarian issues a book to a member.', 'Pay fines')
    assert not mentions('anything', '')  # a label with no words is never mandated
    assert mentions('A member can return books and pay fines.', 'Return book')


def check_drift():
    root = shape(ROOT, ROOT_LINES)
    assert drift_warnings(root, root, STATEMENTS) == []  # the generated version itself

    # Removing an element a requirement mandates warns; removing an assumption (no requirement) does not.
    edited = {'elements': [e for e in ROOT['elements'] if e['element_id'] not in ('uc_issue', 'uc_login')]}
    lines = [ROOT_LINES[1]]
    w = drift_warnings(root, shape(edited, lines), STATEMENTS)
    assert [(x['kind'], x['element_id'], x['ref']) for x in w] == [('element_removed', 'uc_issue', 'R-001')], w
    assert 'R-001' in w[0]['message'] and 'Issue book' in w[0]['message']

    # Reverted edit: the element is back, no warning.
    assert drift_warnings(root, shape(ROOT, ROOT_LINES), STATEMENTS) == []

    # Requirement updated to match: R-001 no longer talks about issuing books, so the removal is not a drift.
    changed = {**STATEMENTS, 'st_1': {'ref': 'R-001', 'text': 'The librarian greets every member.'}}
    assert drift_warnings(root, shape(edited, lines), changed) == []

    # A link the requirements do not support. Librarian -> Return book: no requirement mentions both.
    extra = ROOT_LINES + [('it_lib-uc_return', 'association', 'it_lib', 'uc_return', None)]
    w = drift_warnings(root, shape(ROOT, extra), STATEMENTS)
    assert [(x['kind'], x['element_id']) for x in w] == [('relationship_added', 'it_lib-uc_return')], w
    # ... until a requirement is changed to mention both ends.
    both = {**STATEMENTS, 'st_1': {'ref': 'R-001', 'text': 'The librarian issues a book and also handles the return of a book.'}}
    assert drift_warnings(root, shape(ROOT, extra), both) == []
    # An AI edit that only gives elements new ids (same kind and names) is not a drift.
    renumbered = {'elements': [{**e, 'element_id': 'n_' + e['element_id']} for e in ROOT['elements']]}
    new_lines = [(f'n_{i}', k, 'n_' + s_, 'n_' + t_, l) for i, k, s_, t_, l in ROOT_LINES]
    assert drift_warnings(root, shape(renumbered, new_lines), STATEMENTS) == []
    # A relationship that was already there is not new.
    assert drift_warnings(shape(ROOT, extra), shape(ROOT, extra), STATEMENTS) == []


def diagram(did, title, elements, **extra):
    return {'id': did, 'title': title, 'version': 1, 'elements': elements, **extra}


def check_naming():
    a = diagram('dg_1', 'Use case', [el('it_lib', 'Librarian', 'actor', 'it_lib'), el('uc', 'Issue book')])
    b = diagram('dg_2', 'Class', [el('it_lib', 'Library staff', 'class', 'it_lib'), el('c2', 'Loan', 'class', 'it_loan')])
    c = diagram('dg_3', 'DFD', [el('x', 'Librarian', 'actor', 'it_lib2'), el('y', 'Loan', 'class', 'it_loan')])
    issues = naming_issues([a, b, c])
    assert [i['model_item_id'] for i in issues] == ['it_lib'], issues  # it_lib2 shares a name but is another item
    names = {n['label']: [d['diagram_id'] for d in n['diagrams']] for n in issues[0]['names']}
    assert names == {'Librarian': ['dg_1'], 'Library staff': ['dg_2']}, names
    assert naming_issues([a, diagram('dg_4', 'Again', [el('q', '  Librarian ', 'actor', 'it_lib')])]) == []  # spacing only


def check_rename():
    d = {'elements': [el('it_lib', 'Library staff', 'actor', 'it_lib', ['st_1']), el('uc', 'Issue book', 'use_case')],
         'spec': {'actors': [{'id': 'it_lib', 'name': 'Library staff'}], 'usecases': [{'id': 'uc', 'name': 'Issue book'}]},
         'plantuml_source': '@startuml\nactor "Library staff" as A\nusecase "Issue book" as U\nA --> U\n@enduml',
         'svg': '<svg><text x="1">Library staff</text><text>Issue book</text></svg>'}
    r = rename_in_diagram(d, 'it_lib', 'Librarian')
    assert r['elements'][0]['label'] == 'Librarian' and r['elements'][1]['label'] == 'Issue book'
    assert r['spec']['actors'][0]['name'] == 'Librarian' and r['spec']['usecases'][0]['name'] == 'Issue book'
    assert 'actor "Librarian" as A' in r['plantuml_source'] and 'Library staff' not in r['plantuml_source']
    assert '>Librarian<' in r['svg'] and 'Library staff' not in r['svg'] and r['was'] == ['Library staff']
    assert rename_in_diagram({**d, 'elements': r['elements']}, 'it_lib', 'Librarian') is None  # nothing left to change

    # A short label is not replaced inside a longer one.
    d2 = {'elements': [el('b', 'Book', 'class', 'it_book')], 'spec': {},
          'plantuml_source': 'class "Book"\nclass "Book room"\nBook --> "Book room"', 'svg': '<svg/>'}
    out = rename_in_diagram(d2, 'it_book', 'Title')['plantuml_source']
    assert 'class "Title"' in out and 'class "Book room"' in out, out


if __name__ == '__main__':
    check_mentions()
    check_drift()
    check_naming()
    check_rename()
    print('traceability logic test passed')
