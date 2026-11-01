/* Máscaras de entrada — CNPJ, Telefone, CEP e CPF (vanilla JS, sem dependências).
   Auto-aplica a máscara a qualquer campo com o atributo data-mascara. */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-mascara]").forEach(function (campo) {
    campo.addEventListener("input", function () {
      var tipo = campo.dataset.mascara;
      if (tipo === "cnpj") campo.value = formatarCNPJ(campo.value);
      if (tipo === "telefone") campo.value = formatarTelefone(campo.value);
      if (tipo === "cep") campo.value = formatarCEP(campo.value);
      if (tipo === "cpf") campo.value = formatarCPF(campo.value);
    });
  });
});

/* CNPJ: 00.000.000/0000-00 (14 dígitos) */
function formatarCNPJ(valor) {
  var d = valor.replace(/\D/g, "").slice(0, 14);
  if (d.length === 0) return "";
  if (d.length <= 2) return d;
  if (d.length <= 5) return d.replace(/^(\d{2})(\d{0,3})/, "$1.$2");
  if (d.length <= 8) return d.replace(/^(\d{2})(\d{3})(\d{0,3})/, "$1.$2.$3");
  if (d.length <= 12) return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{0,4})/, "$1.$2.$3/$4");
  return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{0,2})/, "$1.$2.$3/$4-$5");
}

/* Telefone adaptativo: (11) 1234-5678 (fixo) ou (11) 91234-5678 (celular) */
function formatarTelefone(valor) {
  var d = valor.replace(/\D/g, "").slice(0, 11);
  if (d.length === 0) return "";
  if (d.length <= 2) return "(" + d;
  if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
  if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
  return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
}

/* CEP: 00000-000 (8 dígitos) */
function formatarCEP(valor) {
  var d = valor.replace(/\D/g, "").slice(0, 8);
  if (d.length === 0) return "";
  if (d.length <= 5) return d;
  return d.replace(/^(\d{5})(\d{0,3})/, "$1-$2");
}

/* CPF: 000.000.000-00 (11 dígitos) */
function formatarCPF(valor) {
  var d = valor.replace(/\D/g, "").slice(0, 11);
  if (d.length === 0) return "";
  if (d.length <= 3) return d;
  if (d.length <= 6) return d.replace(/^(\d{3})(\d{0,3})/, "$1.$2");
  if (d.length <= 9) return d.replace(/^(\d{3})(\d{3})(\d{0,3})/, "$1.$2.$3");
  return d.replace(/^(\d{3})(\d{3})(\d{3})(\d{0,2})/, "$1.$2.$3-$4");
}