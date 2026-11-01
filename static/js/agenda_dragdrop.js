/* Drag and drop da grade: arrasta um agendamento (AGENDADO/CONFIRMADO)
   para um slot livre. O drop dispara um POST HTMX para o endpoint de
   remarcação; a resposta re-renderiza a grade e as mensagens (via OOB). */
(function () {
  var arrastoAtual = null;

  function obterCsrf() {
    var campo = document.querySelector("[name=csrfmiddlewaretoken]");
    return campo ? campo.value : "";
  }

  document.addEventListener("dragstart", function (e) {
    var celula = e.target.closest("[data-agendamento-id]");
    if (!celula) return;
    arrastoAtual = {
      id: celula.dataset.agendamentoId,
      url: celula.dataset.remarcarUrl
    };
    e.dataTransfer.setData("text/plain", arrastoAtual.id);
    e.dataTransfer.effectAllowed = "move";
    celula.classList.add("arrastando");
  });

  document.addEventListener("dragend", function () {
    document.querySelectorAll(".arrastando").forEach(function (el) {
      el.classList.remove("arrastando");
    });
    document.querySelectorAll(".alvo-soltura").forEach(function (el) {
      el.classList.remove("alvo-soltura");
    });
    arrastoAtual = null;
  });

  document.addEventListener("dragover", function (e) {
    var alvo = e.target.closest("[data-slot-livre]");
    if (!alvo || !arrastoAtual) return;
    e.preventDefault(); // necessário para permitir o drop
    e.dataTransfer.dropEffect = "move";
    alvo.classList.add("alvo-soltura");
  });

  document.addEventListener("dragleave", function (e) {
    var alvo = e.target.closest("[data-slot-livre]");
    if (alvo) alvo.classList.remove("alvo-soltura");
  });

  document.addEventListener("drop", function (e) {
    var alvo = e.target.closest("[data-slot-livre]");
    if (!alvo || !arrastoAtual) return;
    e.preventDefault();
    htmx.ajax("POST", arrastoAtual.url, {
      values: {
        slot_id: alvo.dataset.slotId,
        csrfmiddlewaretoken: obterCsrf()
      },
      target: "#grade-container",
      swap: "innerHTML"
    });
    arrastoAtual = null;
  });
})();