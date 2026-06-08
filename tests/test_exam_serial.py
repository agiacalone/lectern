from lectern.exam_serial import canonical_name, student_serial, source_serial_from_tex


def test_canonical_name_ascii():
    assert canonical_name("Jane Smith") == "jane smith"


def test_canonical_name_accents():
    assert canonical_name("María José O'Brien") == "maria jose o'brien"


def test_canonical_name_whitespace():
    assert canonical_name("  Wáng  Wěi  ") == "wang wei"


def test_canonical_name_nfkc():
    # Composed vs decomposed form normalization
    assert canonical_name("Café") == "cafe"


def test_canonical_name_preserves_apostrophe_hyphen_period():
    assert canonical_name("D'Angelo Smith-Jones Jr.") == "d'angelo smith-jones jr."


def test_student_serial_deterministic():
    a = student_serial("DC8C3554", "Jane Smith")
    b = student_serial("DC8C3554", "Jane Smith")
    assert a == b
    assert len(a) == 8
    assert all(c in "0123456789ABCDEF" for c in a)


def test_student_serial_distinct_by_name():
    a = student_serial("DC8C3554", "Jane Smith")
    b = student_serial("DC8C3554", "John Smith")
    assert a != b


def test_student_serial_distinct_by_source():
    a = student_serial("DC8C3554", "Jane Smith")
    b = student_serial("AAAAAAAA", "Jane Smith")
    assert a != b


def test_student_serial_canonical_name_applied():
    # case + accents + whitespace shouldn't affect the hash
    a = student_serial("DC8C3554", "  María JOSÉ O'BRIEN  ")
    b = student_serial("DC8C3554", "maria jose o'brien")
    assert a == b


def test_source_serial_strips_examserial_line():
    src1 = r"\documentclass{article}" "\n" r"\def\examserial{AAAAAAAA}" "\n" r"foo"
    src2 = r"\documentclass{article}" "\n" r"\def\examserial{ZZZZZZZZ}" "\n" r"foo"
    # Different examserial values shouldn't change the computed hash
    assert source_serial_from_tex(src1) == source_serial_from_tex(src2)


def test_source_serial_strips_answers_toggles():
    src_student = r"\documentclass{article}" "\n" r"\answersfalse" "\n" r"foo"
    src_key = r"\documentclass{article}" "\n" r"\answerstrue" "\n" r"foo"
    # Student build and key build should hash identically
    assert source_serial_from_tex(src_student) == source_serial_from_tex(src_key)


def test_source_serial_strips_key_suffix():
    src_student = r"Final Exam (Variant A)" "\n" r"some content"
    src_key = r"Final Exam (Variant A) --- KEY" "\n" r"some content"
    assert source_serial_from_tex(src_student) == source_serial_from_tex(src_key)


def test_source_serial_content_sensitive():
    src1 = "question one"
    src2 = "question two"
    assert source_serial_from_tex(src1) != source_serial_from_tex(src2)


def test_source_serial_format():
    s = source_serial_from_tex("any content")
    assert len(s) == 8
    assert all(c in "0123456789ABCDEF" for c in s)
