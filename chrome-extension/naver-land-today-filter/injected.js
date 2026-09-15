(function () {
  console.log('[Today Filter] API Interceptor Loaded');

  function todayCompact() {
    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    return `${yyyy}${mm}${dd}`;
  }

  function todayDashed() {
    const now = new Date();
    const yyyy = String(now.getFullYear());
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  // 지도 검색 화면(/map)은 articleClusters, boundedArticlesCount, clusteredArticles 같은
  // 엔드포인트도 쓰기 때문에, 매칭을 '/api/articles' 정확 경로 대신 'article' 포함 여부로
  // 넓힌다. 아래 두 형태에 해당 안 되는 응답(클러스터 집계 등)은 그대로 통과시키므로 안전하다.
  function shouldIntercept(url) {
    return typeof url === 'string' && /article/i.test(url);
  }

  // boundedArticlesCount는 리스트 없이 숫자 하나(result.totalCount)만 내려주는 순수 집계
  // API라, 그 응답 자체만 봐서는 "오늘 매물이 몇 개인지" 알 방법이 없다. 대신 직전에
  // clusteredArticles를 걸러내면서 알아낸 개수를 기억해뒀다가 여기서 그 값으로 덮어쓴다.
  // (지도를 이동/줌하면 같은 화면 범위에 대해 두 API가 거의 같이 호출되는 걸 실측으로 확인.)
  let lastTodayCount = null;

  // 네이버가 화면마다 다른 API 형태를 쓴다는 게 실측으로 확인됨 (2026-09-11):
  // - 단지 상세페이지(complex-scoped)는 data.articleList가 평탄한 배열이고, 날짜 필드가
  //   articleConfirmYmd(대시 없는 "20260911" 형태)이다.
  // - 지도 검색(/map)의 clusteredArticles는 data.result.list가 배열이고, 각 항목의
  //   representativeArticleInfo.verificationInfo.articleConfirmDate가 날짜(대시 있는
  //   "2026-09-11" 형태)이다. 화면에 실제로 렌더링되는 행은 이 representativeArticleInfo
  //   기준이라, 묶음 안의 개별 매물(duplicatedArticleInfo.articleInfoList)까지 건드릴
  //   필요 없이 대표 매물의 날짜만 보고 그 그룹 행을 보이거나 숨기면 된다.
  // - boundedArticlesCount는 위와 똑같은 껍데기(result.totalCount)를 쓰지만 list는 항상
  //   빈 배열이라, URL로 따로 구분해서 처리한다.
  function filterToToday(data, url) {
    if (/boundedArticlesCount/i.test(url || '')) {
      if (typeof data?.result?.totalCount === 'number' && lastTodayCount !== null) {
        data.result.totalCount = lastTodayCount;
      }
      return data;
    }

    if (Array.isArray(data?.articleList)) {
      const today = todayCompact();
      data.articleList = data.articleList.filter(
        (article) => article.articleConfirmYmd === today
      );
      return data;
    }

    if (Array.isArray(data?.result?.list)) {
      const today = todayDashed();
      data.result.list = data.result.list.filter(
        (item) => item?.representativeArticleInfo?.verificationInfo?.articleConfirmDate === today
      );
      if (typeof data.result.totalCount === 'number') {
        data.result.totalCount = data.result.list.length;
      }
      if (data.result.list.length > 0) {
        lastTodayCount = data.result.list.length;
      }
      return data;
    }

    return data;
  }

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';

    if (shouldIntercept(url)) {
      try {
        const data = await response.clone().json();
        const filtered = filterToToday(data, url);
        return new Response(JSON.stringify(filtered), {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      } catch (err) {
        console.error('[Today Filter] fetch JSON parsing error:', err);
      }
    }

    return response;
  };

  // 이 사이트의 지도 검색 화면은 fetch가 아니라 XMLHttpRequest로 데이터를 받아오므로
  // (Network 탭 Type=xhr로 실측 확인), fetch 훅만으로는 아무것도 가로채지 못한다.
  // XHR은 responseText/response가 프로토타입 getter라 직접 대입이 안 되고, 인스턴스에
  // own property로 덮어써야(defineProperty) 실제 페이지 코드가 읽는 값이 바뀐다.
  const OriginalXHR = window.XMLHttpRequest;
  const originalOpen = OriginalXHR.prototype.open;
  const originalSend = OriginalXHR.prototype.send;

  OriginalXHR.prototype.open = function (method, url, ...rest) {
    this.__todayFilterUrl = url;
    return originalOpen.call(this, method, url, ...rest);
  };

  OriginalXHR.prototype.send = function (...args) {
    if (shouldIntercept(this.__todayFilterUrl)) {
      this.addEventListener('load', function () {
        try {
          const responseType = this.responseType;
          const raw = responseType === '' || responseType === 'text'
            ? this.responseText
            : this.response;
          const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
          const filtered = filterToToday(data, this.__todayFilterUrl);

          if (responseType === '' || responseType === 'text') {
            const filteredText = JSON.stringify(filtered);
            Object.defineProperty(this, 'responseText', { value: filteredText, configurable: true });
            Object.defineProperty(this, 'response', { value: filteredText, configurable: true });
          } else {
            Object.defineProperty(this, 'response', { value: filtered, configurable: true });
          }
        } catch (err) {
          console.error('[Today Filter] XHR JSON parsing error:', err);
        }
      });
    }
    return originalSend.apply(this, args);
  };
})();
