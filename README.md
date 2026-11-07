# BDC Nutri — Monitor das bases alimentares

Este repositório serve **somente** para acompanhar e publicar pacotes de dados nutricionais públicos. Não hospeda o programa de pacientes nem backups.

## Fontes

- **TACO (4ª edição, 2011):** verificação de distribuições digitais na interface do BDC Nutri; não corresponde a uma nova edição científica.
- **IBGE POF 2008–2009:** verificação da assinatura do arquivo público oficial; quando mudar, exige conversão e validação antes de qualquer instalação.
- **USDA Foundation Foods:** consulta a página oficial e prepara pacote JSON compatível caso encontre lançamento ou correção.
- **USDA SR Legacy:** edição final de 2018, sem novas edições previstas.
- **TBCA e Tucunduva:** aguardam autorização/licença; sem cópia de seus dados.

## Como funciona

O arquivo `.github/workflows/monitorar-bases.yml` pode executar diariamente via **GitHub Actions** e atualizar `site/bdc-bases-manifest.json` e, quando aplicável, `site/food-packs/`.

No programa BDC Nutri, configure em **Atualizações > Configuração da sincronização online** o endereço completo do catálogo:

`https://raw.githubusercontent.com/rosianeassef401/bdc-nutri-bases/main/site/bdc-bases-manifest.json`

O catálogo é apenas um índice: não é possível instalar um arquivo novo sem conversão, validação e verificação da assinatura SHA-256. A alteração de formato ou método de uma fonte pode exigir revisão manual.

**NÃO enviar a este repositório:** dados de pacientes, dietas individuais, fotos, backups, senhas, prontuários ou o HTML completo do aplicativo. O repositório é público.

## Referências

- USDA: https://fdc.nal.usda.gov/download-datasets/
- IBGE: https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2008_2009/Tabelas_de_Composicao_Nutricional_dos_Alimentos_Consumidos_no_Brasil/
