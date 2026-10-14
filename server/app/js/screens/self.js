// 본인 확인 화면 (#/self): 사고 대응 패널을 화면 전체에 보여 줍니다.
// 확인 로직은 incident/panel.js 로 옮겼고, 모든 메뉴 위에 뜨는 사고 대응 레이어(incident/layer.js)도 같은 것을 씁니다.
import { createIncidentPanel } from "../incident/panel.js";

export function render(container, { api, statusPoller, config }) {
  const panel = createIncidentPanel({ api, statusPoller, config });
  container.append(panel.element);
  return panel.destroy;
}
