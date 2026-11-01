// What do people want when they search a topic? (JavaScript port of intent.py)
// Plain word lists, no model; the first match wins. Phrases no list catches stay "other".
const PATTERNS = {
  how_to: /하는\s?법|방법|사용법|설정|끄기|끄는|켜기|켜는|해제|초기화|연결|설치|다운로드|옮기기|바꾸기|찾기|확인|등록|교체\s?주기|교환\s?주기|공략|재부팅|강제|스크린샷|캡쳐|캡처|녹화|화면분할|제거|안꺼지|충전소|\bhow to\b|\bhow do\b|\bsettings?\b|\bsetup\b|\binstall\b|\bdownload\b|\bturn (?:on|off)\b|\breset\b|\bfix\b/,
  problems: /고장|결함|리콜|오류|안됨|안 됨|안되|문제|논란|단점|부작용|위험|화재|폭발|멀미|후회|망함|사고|피해|한계|\brecall\b|\bproblems?\b|\bissues?\b|\bnot working\b|\brisks?\b|\bchallenges?\b|\bdangers?\b/,
  policy: /보조금|지원금|국고|세금|자동차세|취등록세|환경부|통행료|톨비|번호판|혜택|규제|법안|정책|정부|지원사업|예산|\blaws?\b|\bregulations?\b|\bpolicy\b|\bgovernment\b|\bsubsid(?:y|ies)\b|\btax\b/,
  investing: /관련주|대장주|주가|주식|종목|\betfs?\b|\bstocks?\b|\bshares?\b|\binvest(?:ing|ment|ments)?\b/,
  buying: /가격|최저가|할인|구매|구입|추천|순위|비교|후기|리뷰|중고|싸게|요금|비용|유지비|수리비|시세|렌트|리스|쿠폰|스토어|사전예약|자급제|구독|충전기|\bprice\b|\bcost\b|\bbuy\b|\bbest\b|\bvs\b|\breviews?\b|\bdeals?\b|\bcheap\b|\bused\b|\bfor sale\b/,
  definition: /뜻|이란|란$|의미|정의|뭐야|뭔가요|영어로|예시|\bmeaning\b|\bwhat is\b|\bdefinition\b|\bexamples?\b|\bdefine\b/,
  jobs: /채용|취업|연봉|인턴|\bjobs?\b|\bcareers?\b|\bsalary\b|\bhiring\b|\bengineer\b|\binternship\b/,
  events: /컨퍼런스|박람회|전시회|전시|포럼|세미나|행사|서밋|\bconference\b|\bsummit\b|\bexpo\b|\bevents?\b|\bforum\b/,
  learning: /강의|강좌|교육|논문|자격증|책|\bcourses?\b|\bpapers?\b|\bpdf\b|\bbooks?\b|\btutorials?\b|\bcertificat|\blearn\b|\buniversity\b/,
  companies: /기업|회사|업체|스타트업|\bcompan(?:y|ies)\b|\bstartups?\b|\bnvidia\b|\btesla\b|\bgoogle\b|\bopenai\b/,
  industries: /산업|제조|물류|의료|국방|농업|\bindustry\b|\bindustries\b|\bmanufacturing\b|\bhealthcare\b|\blogistics\b|\bfactory\b/,
  technology: /기술|원리|구조|배터리|모터|센서|반도체|회생제동|\btechnology\b|\btechnologies\b|\barchitecture\b|\bsensors?\b|\bchips?\b|\bmodels?\b/,
  outlook: /전망|미래|시장|규모|판매량|트렌드|캐즘|\bmarket\b|\bfuture\b|\bforecast\b|\boutlook\b|\btrends?\b/,
  product_info: /출시일|출시|스펙|사양|색상|크기|무게|종류|시간|수명|모델|\brelease date\b|\bspecs?\b|\bdimensions\b|\bsuv\b|\b[a-z]{1,3}\s?\d{1,3}\b|[가-힣]{2,}\s?\d{1,2}(?:\s|$)/,
  news: /뉴스|기사|디시|갤러리|카페|동호회|\bnews\b|\breddit\b|\bforums?\b/,
};

function classify(phrase, topic) {
  const rest = phrase.toLowerCase().replace(topic.toLowerCase(), " ").trim();
  for (const [intent, pattern] of Object.entries(PATTERNS)) if (pattern.test(rest)) return intent;
  return "other";
}

// Returns [how the phrases were sorted, [{intent, share, examples}]].
export function searchIntent(related, topic, maxPhrases = 300) {
  const totals = new Map(), examples = {};
  for (const r of related.slice(0, maxPhrases)) {
    const intent = classify(r.phrase, topic);
    totals.set(intent, (totals.get(intent) || 0) + r.times_suggested);
    (examples[intent] ||= []).push(r.phrase);
  }
  const all = [...totals.values()].reduce((a, b) => a + b, 0) || 1;
  return ["word lists", [...totals].sort((a, b) => b[1] - a[1]).map(([intent, n]) => ({
    intent, share: Math.round((n / all) * 100) / 100, examples: examples[intent].slice(0, 5),
  }))];
}
