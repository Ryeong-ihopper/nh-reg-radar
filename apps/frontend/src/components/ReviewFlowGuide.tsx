import type { OperationalCapabilities } from "../api/operational";
import { Link } from "react-router-dom";

export function ReviewFlowGuide({ capabilities }: { capabilities?: OperationalCapabilities }) {
  return <details className="review-flow-guide">
    <summary>심의 흐름과 적용 기준 보기</summary>
    <ol className="review-flow-diagram">
      <li><strong>1. 상품·매체 확인</strong><span>기본 템플릿과 함께 적용할 운용상품 기준을 선택합니다.</span></li>
      <li><strong>2. 원문 추출</strong><span>본문·라벨·줄·좌표를 연결하고 판독이 불확실한 부분을 표시합니다.</span></li>
      <li><strong>3. 적용 항목 선정</strong><span>기본 필수 항목을 모두 펼치고 실제 조건·예외를 구분합니다.</span></li>
      <li><strong>4. 광고 근거 찾기</strong><span>검사마다 라벨·단어·원문 관계를 이용해 근거를 확보합니다.</span></li>
      <li><strong>5. 검사와 종합</strong><span>코드는 형식·수치·조건을, LLM은 의미와 정보 역할을 확인합니다. 두 방식을 함께 쓰는 항목도 있습니다.</span></li>
      <li><strong>6. 결과 확인</strong><span>원문 인용과 위치를 확인합니다. 외부자료·시각 확인·추출 불확실성은 확인필요로 남습니다.</span></li>
    </ol>
    <div className="review-flow-explanation">
      <p><Link to="/review-criteria">템플릿·보완 규정 구조화 작업대장 열기</Link></p>
      <p><strong>검색은 두 곳에서 쓰입니다.</strong> 광고 내용으로 보완 후보를 발견하는 방향과, 적용할 검사에서 광고 증거를 찾는 방향입니다. 필수 항목은 검색 점수와 관계없이 검사합니다. 검색에서 못 찾았다는 이유만으로 문구 누락을 확정하지 않습니다.</p>
      <p>라벨은 근거를 찾는 힌트입니다. 회사명·상품명도 실제 원문과 역할을 확인합니다. 임베딩은 항목별 비교 검증 후 보조 사용 여부를 정합니다.</p>
      <p className="panel-note">{capabilities?.sourcePolicy === "template-plus-v2" ? "현재 선택 템플릿과 승인된 보완 규칙을 사용합니다." : "현재 운영은 선택 템플릿을 사용합니다. 보완 32개와 추가 후보는 검토·구조화 중이며 자동 판정에 일괄 추가하지 않습니다."} 원문 예시는 완전일치 의무가 아니며, 심의정답은 평가에만 사용합니다.</p>
    </div>
  </details>;
}
