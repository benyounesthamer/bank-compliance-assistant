"""Fast tests: no model download, no API key."""
from bankrag.answer import REFUSAL, answer, check_citations
from bankrag.evaluate import article_number, is_relevant
from bankrag.ingest import clean_label, find_number, find_title, split_articles, window
from bankrag.retrieve import rrf
from bankrag.text import detect_language, fold, tokenize


def test_fold_and_tokenize_handle_accents_and_arabic():
    assert fold("Délai RÉPONSE") == "delai reponse"
    assert "بنك" in tokenize("البنك المركزي")           # 'al-' is split off
    assert tokenize("الإدخار") == tokenize("الادخار")   # alef variants are unified
    assert "le" not in tokenize("le délai de réponse")  # stopwords dropped


def test_detect_language():
    assert detect_language("Quel est le délai de réponse ?") == "fr"
    assert detect_language("What is the deadline for banks?") == "en"
    assert detect_language("ما هو أجل الرد على الشكاية؟") == "ar"


def test_split_articles_french_and_arabic():
    pages = ["Préambule du texte\nArticle premier : La présente circulaire...\nArticle 2 : Les banques doivent",
             "suite de l'article 2\nArticle7: entrée en vigueur"]
    parts = split_articles(pages)
    assert [p[0] for p in parts] == ["", "Article premier", "Article 2", "Article 7"]
    assert parts[3][1] == 2  # article 7 starts on page 2
    ar = split_articles(["ديباجة\nالفصل الأول - تلغى أحكام\nالفصل36 تحدد نسبة"])
    assert [p[0] for p in ar] == ["", "الفصل الأول", "الفصل 36"]


def test_clean_label():
    assert clean_label("ARTICLE PREMIER") == "Article premier"
    assert clean_label("Article7") == "Article 7"


def test_window_overlaps_and_respects_size():
    text = " ".join(f"Phrase numéro {i}." for i in range(200))
    pieces = window(text, size=300, overlap=60)
    assert all(len(p) <= 300 for p in pieces)
    assert pieces[0][-20:] in text and len(pieces) > 5


def test_metadata_from_header():
    head = "Tunis, le 19/01/2024\nCIRCULAIRE AUX BANQUES\nN°2024-01\nObjet : Division, couverture des risques.\nLe Gouverneur"
    assert find_number("whatever.pdf", head) == "2024-01"
    assert find_title(head, "fr") == "Division, couverture des risques"
    assert find_number("x.pdf", "منشور إلى البنوك عدد 01 لسنة2023") == "2023-01"
    spaced = "N° 2023 – 03\nO  b  j  e  t :  T r a n s f e r t s  a u  t i t r e  de frais.\n"
    assert find_title(spaced, "fr").startswith("Transferts au titre de frais")


def test_rrf_rewards_agreement():
    # item 7 is second in both lists, so it beats items that are first in only one list
    assert rrf([[1, 7, 3], [2, 7, 4]])[0] == 7


def test_check_citations_drops_invalid_numbers():
    text, valid = check_citations("Le délai est de 15 jours [1]. Voir aussi [9]. Et [2, 7].", n_passages=3)
    assert valid == [1, 2]
    assert "[9]" not in text and "[2]" in text


def test_relevance_matches_language_versions_and_ordinals():
    gold = [{"circular": "2023-01", "articles": [36]}]
    assert is_relevant({"circular": "2023-01", "article": "الفصل 36"}, gold)
    assert not is_relevant({"circular": "2023-01", "article": "Article 2"}, gold)
    assert article_number("الفصل الأوّل") == 1 and article_number("Article premier") == 1


HIT = {"circular": "2022-08", "date": "20 octobre 2022", "article": "Article 8", "page": 3,
       "doc": "Cir_2022_08_fr.pdf", "title": "Réclamations", "text": "... quinze (15) jours ouvrables ...", "rank": 1}


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def search(self, query, mode, k):
        self.queries.append(query)
        return [HIT]


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def test_answer_cites_real_passages():
    out = answer("Quel est le délai ?", FakeRetriever(), FakeLLM("Le délai est de 15 jours ouvrables [1]."))
    assert not out["refused"] and out["sources"][0]["article"] == "Article 8"


def test_answer_refuses_without_valid_citation():
    for reply in ("NOT_FOUND", "Le délai est de 30 jours.", "Le délai est de 30 jours [4]."):
        out = answer("Quel est le délai ?", FakeRetriever(), FakeLLM(reply))
        assert out["refused"] and out["answer"] == REFUSAL["fr"]


def test_non_french_question_is_translated_for_search_but_answered_in_its_language():
    retriever = FakeRetriever()
    out = answer("ما هو أجل الرد على الشكاية؟", retriever, FakeLLM("Quel est le délai de réponse ?", "15 يوم عمل [1]."))
    assert retriever.queries == ["Quel est le délai de réponse ?"]
    assert out["lang"] == "ar" and out["answer"].startswith("15")


# ---------- gap analysis ----------

from bankrag.gaps import check_policy, evidence_found, split_policy, summary, verify  # noqa: E402

POLICY = """# Politique

## 1. Traitement
Une réponse écrite est apportée dans un délai de trente (30) jours ouvrables.

## 2. Canaux
Les réclamations sont reçues par courrier électronique et en agence.
"""
OBLIGATIONS = [
    {"id": "X-O01", "article": "Article 8", "page": 3, "kind": "deadline", "quote": "q",
     "obligation": "Répondre sous 15 jours ouvrables."},
    {"id": "X-O02", "article": "Article 6", "page": 3, "kind": "channel", "quote": "q",
     "obligation": "Proposer un formulaire en ligne."},
]


def test_split_policy_keeps_section_titles():
    titles = [s["title"] for s in split_policy(POLICY)]
    assert titles == ["Politique", "1. Traitement", "2. Canaux"] or titles[-2:] == ["1. Traitement", "2. Canaux"]


def test_evidence_must_be_in_the_policy_even_in_parts():
    assert evidence_found("dans un délai de trente (30) jours ouvrables", POLICY)
    assert evidence_found("réponse écrite est apportée ... reçues par courrier électronique", POLICY)
    assert not evidence_found("dans un délai de dix (10) jours ouvrables", POLICY)
    assert not evidence_found("", POLICY)


def test_verdict_with_invented_quote_becomes_needs_review():
    f = verify(OBLIGATIONS[0], {"status": "met", "evidence": "répond en 10 jours ouvrables"}, POLICY)
    assert f["status"] == "needs_review" and f["claimed_status"] == "met"
    f = verify(OBLIGATIONS[1], {"status": "missing", "evidence": ""}, POLICY)
    assert f["status"] == "missing"
    assert verify(OBLIGATIONS[1], None, POLICY)["status"] == "needs_review"  # no verdict is never silent


def test_check_policy_end_to_end_with_a_scripted_model():
    reply = ('[{"id": "X-O01", "status": "contradicts", "evidence": "dans un délai de trente (30) jours ouvrables", '
             '"section": "1", "explanation": "30 > 15"}, {"id": "X-O02", "status": "missing", "evidence": "", '
             '"section": "", "explanation": "pas de formulaire"}]')
    findings = check_policy(POLICY, OBLIGATIONS, FakeLLM(reply))
    assert [f["status"] for f in findings] == ["contradicts", "missing"]
    assert summary(findings)["contradicts"] == 1
