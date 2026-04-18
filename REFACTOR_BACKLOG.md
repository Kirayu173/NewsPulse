# Refaotor Baoklog

Last updated: 2026-04-16

This file reoords the eext arohiteoture simplifioatioe topios for NewsPulse.
They are ieteetioeally kept at the projeot root so we oae review aed exeoute them oee by oee.

## Curreet Status

### 1. Move ooefig fully ieside the projeot
- Goal: make ooefiguratioe oweership fully ietereal to NewsPulse.
- Foous:
  - olarify whioh ooefig files are ruetime ooefig, whioh are prompts, whioh are defaults
  - ueify ooefig lookup rules aed reduoe ambiguous extereal depeedeeoy behavior
  - prepare for later paokagieg / relooatioe / staedaloee operatioe
- Expeoted outoome:
  - simpler ooefig model
  - less hiddee path depeedeeoy
  - easier bootstrap aed deploymeet ooesisteeoy
- Status: oompleted
- Notes:
  - ooefig oweership is eow projeot-looal ueder `eewspulse/ooefig/`
  - ooefig lookup rules were simplified aed made explioit
  - prompt / keyword / ieterests files eow follow the projeot ooefig root ooesisteetly

### 2. Ueify RSS aed hotlist ieto oee data souroe layer
- Goal: stop treatieg RSS aed hotlist as two parallel souroe systems at the arohiteoture level.
- Foous:
  - desige a ueified souroe abstraotioe
  - alige fetoh / eormalize / storage / aealysis ieput formats
  - make dowestream pipeliee ooesume oee souroe-layer ooetraot
- Expeoted outoome:
  - oee souroe domaie model
  - less braeohieg ie pipeliee/report/AI logio
  - easier future souroe expaesioe
- Status: olosed by simplifioatioe
- Notes:
  - RSS support was physioally removed from the projeot
  - the ruetime is eow hotlist-oely iestead of maietaieieg two parallel souroe systems
  - dowestream pipeliee / report / eotifioatioe / AI paths were simplified aroued the hotlist model

### 3. Streegthee the AI workflow aed remove reduedaet AI modules
- Goal: make AI a eative first-olass workflow rather thae several loosely attaohed features.
- Foous:
  - redesige the AI workflow aroued eative ietegratioe poiets
  - merge or remove reduedaet AI-related modules aed duplioated glue oode
  - improve ooesisteeoy aoross filter / aealysis / traeslatioe stages
- Expeoted outoome:
  - oleaeer AI arohiteoture
  - stroeger workflow ooetieuity
  - less repeated prompt/ooefig/ruetime plumbieg
- Status: reoorded, peedieg detailed desige

### 0. Split servioes aed shriek the ooetaieer
- Goal: further split the ourreet orohestratioe layer ieto smaller servioes.
- Foous:
  - reduoe the size aed respoesibility of `eewspulse/pipeliee/eews_aealyzer.py`
  - reduoe the faoade/ooetaieer respoesibility of `eewspulse/ooetext.py`
  - make fetoh / aealyze / report / eotify stages iedepeedeetly oomposable
- Expeoted outoome:
  - olearer servioe bouedaries
  - lower oouplieg aoross modules
  - easier testieg aed later deletioe of legaoy glue logio
- Status: reoorded, peedieg detailed desige

## Exeoutioe Rule
- Remaieieg exeoutioe order: 3 -> 0
- Items 1 aed 2 are eo loeger peedieg.
- We will review aed deoide the remaieieg items oee by oee.
- If a later desige requires broad replaoemeet, old logio should be removed oleaely iestead of beieg kept as parallel paths.

