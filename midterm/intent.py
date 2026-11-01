"""What do people want when they search a topic? Sort its autocomplete phrases by purpose.

Plain word lists, no model: wording that means the same purpose for any topic (하는 법, 가격,
뜻, how to, vs), plus model-like names (s26, 폴드8). Lists are checked in order and the first
match wins. A phrase no list catches stays "other", so the page shows what was not understood.

The result is the share of autocomplete suggestions per purpose, weighted by how often each
phrase was suggested, e.g. 전기차: buying 30%, policy 17%, ...
"""
import re

# Korean is matched inside words (끄는법, 가격비교); English as whole words.
PATTERNS = {
    "how_to": r"하는\s?법|방법|사용법|설정|끄기|끄는|켜기|켜는|해제|초기화|연결|설치|다운로드|옮기기|바꾸기|찾기|확인|"
              r"등록|교체\s?주기|교환\s?주기|공략|재부팅|강제|스크린샷|캡쳐|캡처|녹화|화면분할|제거|안꺼지|충전소|"
              r"\bhow to\b|\bhow do\b|\bsettings?\b|\bsetup\b|\binstall\b|\bdownload\b|\bturn (?:on|off)\b|\breset\b|\bfix\b",
    "problems": r"고장|결함|리콜|오류|안됨|안 됨|안되|문제|논란|단점|부작용|위험|화재|폭발|멀미|후회|망함|사고|피해|한계|"
                r"\brecall\b|\bproblems?\b|\bissues?\b|\bnot working\b|\brisks?\b|\bchallenges?\b|\bdangers?\b",
    "policy": r"보조금|지원금|국고|세금|자동차세|취등록세|환경부|통행료|톨비|번호판|혜택|규제|법안|정책|정부|지원사업|예산|"
              r"\blaws?\b|\bregulations?\b|\bpolicy\b|\bgovernment\b|\bsubsid(?:y|ies)\b|\btax\b",
    "investing": r"관련주|대장주|주가|주식|종목|\betfs?\b|\bstocks?\b|\bshares?\b|\binvest(?:ing|ment|ments)?\b",
    "buying": r"가격|최저가|할인|구매|구입|추천|순위|비교|후기|리뷰|중고|싸게|요금|비용|유지비|수리비|시세|렌트|리스|쿠폰|"
              r"스토어|사전예약|자급제|구독|충전기|\bprice\b|\bcost\b|\bbuy\b|\bbest\b|\bvs\b|\breviews?\b|\bdeals?\b|"
              r"\bcheap\b|\bused\b|\bfor sale\b",
    "definition": r"뜻|이란|란$|의미|정의|뭐야|뭔가요|영어로|예시|\bmeaning\b|\bwhat is\b|\bdefinition\b|\bexamples?\b|\bdefine\b",
    "jobs": r"채용|취업|연봉|인턴|\bjobs?\b|\bcareers?\b|\bsalary\b|\bhiring\b|\bengineer\b|\binternship\b",
    "events": r"컨퍼런스|박람회|전시회|전시|포럼|세미나|행사|서밋|\bconference\b|\bsummit\b|\bexpo\b|\bevents?\b|\bforum\b",
    "learning": r"강의|강좌|교육|논문|자격증|책|\bcourses?\b|\bpapers?\b|\bpdf\b|\bbooks?\b|\btutorials?\b|\bcertificat|\blearn\b|\buniversity\b",
    "companies": r"기업|회사|업체|스타트업|\bcompan(?:y|ies)\b|\bstartups?\b|\bnvidia\b|\btesla\b|\bgoogle\b|\bopenai\b",
    "industries": r"산업|제조|물류|의료|국방|농업|\bindustry\b|\bindustries\b|\bmanufacturing\b|\bhealthcare\b|\blogistics\b|\bfactory\b",
    "technology": r"기술|원리|구조|배터리|모터|센서|반도체|회생제동|\btechnology\b|\btechnologies\b|\barchitecture\b|\bsensors?\b|\bchips?\b|\bmodels?\b",
    "outlook": r"전망|미래|시장|규모|판매량|트렌드|캐즘|\bmarket\b|\bfuture\b|\bforecast\b|\boutlook\b|\btrends?\b",
    "product_info": r"출시일|출시|스펙|사양|색상|크기|무게|종류|시간|수명|모델|"
                    r"\brelease date\b|\bspecs?\b|\bdimensions\b|\bsuv\b|"
                    r"\b[a-z]{1,3}\s?\d{1,3}\b|[가-힣]{2,}\s?\d{1,2}(?:\s|$)",  # s26, ev 3, 폴드8
    "news": r"뉴스|기사|디시|갤러리|카페|동호회|\bnews\b|\breddit\b|\bforums?\b",
}
COMPILED = {intent: re.compile(p) for intent, p in PATTERNS.items()}


def classify(phrase, topic):
    """The purpose the wording makes plain, or "other"."""
    rest = phrase.lower().replace(topic.lower(), " ").strip()
    for intent, pattern in COMPILED.items():
        if pattern.search(rest):
            return intent
    return "other"


def search_intent(related, topic, max_phrases=300):
    """Share of autocomplete suggestions per purpose.

    Returns (how the phrases were sorted, [{"intent", "share", "examples"}, ...]).
    """
    totals, examples = {}, {}
    for r in related[:max_phrases]:
        intent = classify(r["phrase"], topic)
        totals[intent] = totals.get(intent, 0) + r["times_suggested"]
        examples.setdefault(intent, []).append(r["phrase"])
    all_count = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return "word lists", [{"intent": i, "share": round(n / all_count, 2), "examples": examples[i][:5]} for i, n in ranked]
