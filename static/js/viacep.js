(function () {
  "use strict";

  // ViaCEP chama a cidade de "localidade" — mapa: campo do form → campo da API
  const MAPA_VIACEP = {
    logradouro: "logradouro",
    bairro: "bairro",
    cidade: "localidade",
    uf: "uf",
  };

  function dica(campo, texto, ok) {
    let el = campo.parentElement.querySelector(".cep-dica");
    if (!el) {
      el = document.createElement("div");
      campo.parentElement.appendChild(el);
    }
    el.textContent = texto;
    el.className = "cep-dica small mt-1 " + (ok ? "text-success" : "text-danger");
  }

  // Formset: cada endereço é um .card (escopo = 1 linha).
  // Form simples (profissional): escopo = o <form> inteiro.
  function escopoDoCampo(campo) {
    return campo.closest(".card") || campo.closest("form") || document;
  }

  async function preencher(campo) {
    const cep = campo.value.replace(/\D/g, "");
    if (cep.length !== 8) {
      if (campo.value.trim() !== "") dica(campo, "CEP incompleto — digite os 8 dígitos.", false);
      return;
    }

    const escopo = escopoDoCampo(campo);

    campo.setAttribute("readonly", "readonly");   // evita busca duplicada enquanto carrega
    dica(campo, "Buscando CEP…", true);

    try {
      const resposta = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const dados = await resposta.json();

      if (dados.erro) {
        dica(campo, "CEP não encontrado — preencha o endereço manualmente.", false);
        return;
      }

      for (const [nomeCampo, nomeApi] of Object.entries(MAPA_VIACEP)) {
        const alvo = escopo.querySelector(`[name$="${nomeCampo}"]`);
        const valor = dados[nomeApi];
        if (!alvo || !valor) continue;
        // Select (UF): só preenche se a option existir
        if (alvo.tagName === "SELECT" && ![...alvo.options].some(o => o.value === valor)) continue;
        alvo.value = valor;
      }

      const complemento = escopo.querySelector('[name$="complemento"]');
      if (complemento && !complemento.value && dados.complemento) {
        complemento.value = dados.complemento;
      }

      dica(campo, "Endereço preenchido pelo CEP.", true);
    } catch (erro) {
      dica(campo, "Não foi possível consultar o CEP agora — preencha manualmente.", false);
    } finally {
      campo.removeAttribute("readonly");
    }
  }

  // Máscara 00000-000 enquanto digita (delegação: cobre formsets e forms simples)
  document.addEventListener("input", (e) => {
    if (e.target.matches('[name$="cep"]')) {
      const digitos = e.target.value.replace(/\D/g, "").slice(0, 8);
      e.target.value = digitos.length > 5
        ? `${digitos.slice(0, 5)}-${digitos.slice(5)}`
        : digitos;
    }
  });

  // Preenchimento via ViaCEP ao sair do campo
  document.addEventListener("change", (e) => {
    if (e.target.matches('[name$="cep"]')) preencher(e.target);
  });
})();