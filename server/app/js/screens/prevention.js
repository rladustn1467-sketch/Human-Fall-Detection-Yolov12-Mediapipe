// 낙상 예방: 콘텐츠 파일(app/content/prevention/*.json)을 읽어 그대로 보여 주는 화면입니다.
// 내용은 팀원이 JSON 파일만 고쳐서 추가합니다 (형식: app/content/prevention/README.md). 화면 코드는 고치지 않아도 됩니다.
import { button, el } from "../ui.js";

const BASE = "content/prevention";
// 콘텐츠 id 는 파일 이름이므로 영문 소문자·숫자·- 만 허용
const ID_RE = /^[a-z0-9-]+$/;

function loadArea(api, id) {
  if (!ID_RE.test(id)) return Promise.reject(new Error(`잘못된 콘텐츠 id: ${id}`));
  return api.content(`${BASE}/${id}.json`);
}

function preparing() {
  return el("p", {}, el("span", { className: "badge" }, "준비 중"), " 내용을 준비하고 있어요.");
}

function isPublished(area) {
  return area.status === "published" && Array.isArray(area.sections) && area.sections.length > 0;
}

// 섹션 한 개: { "heading": "...", "paragraphs": ["..."], "items": ["..."] } (글자만, HTML 은 쓰지 않음)
function section(sec) {
  const node = el("div", { className: "panel" });
  if (sec.heading) node.append(el("p", { className: "lead" }, sec.heading));
  for (const text of sec.paragraphs || []) node.append(el("p", {}, text));
  if (Array.isArray(sec.items) && sec.items.length) {
    node.append(el("ul", { className: "content-list" }, ...sec.items.map((item) => el("li", {}, item))));
  }
  return node;
}

function renderList(container, { api, go }) {
  const list = el("div", {}, el("p", { className: "muted" }, "불러오는 중이에요..."));
  container.append(el("h1", {}, "낙상 예방"), list);
  api.content(`${BASE}/index.json`)
    .then((index) => Promise.all((index.areas || []).map((id) => loadArea(api, id))))
    .then((areas) => {
      list.replaceChildren(...areas.map((area) => el("div", { className: "panel" },
        el("p", { className: "lead" }, area.title),
        el("p", {}, area.summary),
        isPublished(area) ? null : preparing(),
        button("자세히 보기", null, { onClick: () => go(`prevention/${area.id}`) }))));
    })
    .catch(() => list.replaceChildren(el("p", {}, "낙상 예방 정보를 불러오지 못했어요.")));
}

function renderDetail(container, { api, go }, id) {
  const body = el("div", {}, el("p", { className: "muted" }, "불러오는 중이에요..."));
  container.append(body, button("목록으로", null, { onClick: () => go("prevention") }));
  loadArea(api, id)
    .then((area) => {
      body.replaceChildren(el("h1", {}, area.title), el("p", {}, area.summary));
      if (isPublished(area)) body.append(...area.sections.map(section));
      else body.append(el("div", { className: "panel" }, preparing()));
    })
    .catch(() => body.replaceChildren(el("h1", {}, "낙상 예방"), el("p", {}, "이 내용을 불러오지 못했어요.")));
}

export function render(container, context) {
  const [id] = context.params || [];
  if (id) renderDetail(container, context, id);
  else renderList(container, context);
}
