// 화면을 만들 때 쓰는 작은 도우미 (글자는 항상 textContent 로 넣어 안전하게)

// el("p", { className: "muted" }, "글자", 다른요소...)
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// 큰 버튼: button("괜찮아요", "보호자에게 알려요", { className: "safe", onClick })
export function button(label, hint, { className = "", onClick } = {}) {
  const node = el("button", { type: "button", className: `big-button ${className}`.trim() }, label);
  if (hint) node.append(el("small", {}, hint));
  if (onClick) node.addEventListener("click", onClick);
  return node;
}
