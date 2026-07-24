# Care Companion — Glosario colombiano de expresiones ambiguas (salud)

> v0.1 · 23 de julio de 2026 · Ticket: PRE-018

Deriva de `plan.md` PRE-018 (Sprint P1) y `spec.md` §11 (reglas operativas).

## Advertencia obligatoria

Este material es **100% sintético y no clínico**. Es un fixture de referencia lingüística/conversacional para el `InterviewAgent` y el manejo de ambigüedad (`CON-003`), **no** una guía médica, ni un mapeo diagnóstico, ni contenido derivado del dataset del reto (que aún no se ha publicado). Ninguna expresión de este glosario debe usarse para inferir un síntoma, signo o diagnóstico de forma automática.

## Regla transversal (obligatoria, spec §11)

**Ninguna expresión de este glosario se mapea directamente a un síntoma o diagnóstico.** Un dato ambiguo nunca se asume: silencio o coloquialismo no equivale a negación ni a confirmación. Ante cualquiera de estas expresiones, el sistema **siempre** debe formular una pregunta de aclaración contextual antes de registrar cualquier observación estructurada, y debe conservar tanto el texto original del cuidador como la aclaración obtenida.

## Cómo leer cada entrada

- **Expresión:** frase o palabra coloquial tal como podría decirla un cuidador colombiano.
- **Ambigüedad:** el rango de significados posibles que puede cubrir esa expresión (lista no exhaustiva, ejemplos ilustrativos).
- **Regla de aclaración:** la pregunta o tipo de pregunta que el agente debe hacer para desambiguar, sin sugerir la respuesta ni inducirla.

---

| # | Expresión | Ambigüedad | Regla de aclaración |
|---|---|---|---|
| 1 | "me siento maluco/a" / "está maluco/a" | Puede indicar malestar general, dolor, náusea, mareo, decaimiento anímico, o simplemente "no se siente como siempre". | Preguntar de forma abierta qué quiere decir con "maluco" en este caso, ofreciendo categorías amplias (dolor, malestar, náusea, decaimiento) sin asumir ninguna hasta que el cuidador la confirme. |
| 2 | "está decaído/a" | Puede referirse a baja energía física, somnolencia inusual, tristeza/ánimo bajo, o efecto normal del reposo postoperatorio. | Preguntar si se refiere a que duerme más de lo usual, a que está triste/desanimado, o a que no tiene energía para actividades que antes hacía, y desde cuándo. |
| 3 | "le dio duro" | Puede describir dolor intenso, un episodio de malestar fuerte, o una reacción emocional fuerte (llanto, susto), sin especificar qué. | Preguntar concretamente qué fue lo que "le dio duro": dolor, fiebre, llanto, otra cosa, y pedir que lo describa con sus propias palabras. |
| 4 | "tiene guayabo de la anestesia" | Expresión coloquial para malestar post-anestesia; puede cubrir mareo, náusea, somnolencia, desorientación temporal o simple cansancio esperado. | Preguntar si el malestar incluye mareo, ganas de vomitar, dificultad para despertar completamente, o solo cansancio, y si ya ha ido disminuyendo con las horas. |
| 5 | "está aporreado/a" | Puede significar dolor corporal generalizado, molestia al moverse, o simplemente cansancio físico sin dolor específico. | Preguntar si el niño se queja al moverse o al tocarlo en alguna zona particular, o si es una sensación general de cansancio sin dolor localizado. |
| 6 | "está como ido/a" | Puede indicar somnolencia post-anestesia normal, desorientación, falta de respuesta a estímulos, o simplemente que está callado/introvertido. | Preguntar si el niño responde cuando le hablan, reconoce a las personas, y si esto es distinto a su comportamiento habitual antes de la cirugía. |
| 7 | "no ha querido ni jugar" | Puede reflejar dolor, malestar general, cansancio esperado del postoperatorio, o simplemente aburrimiento/mal genio pasajero. | Preguntar desde cuándo no quiere jugar, si se queja de algo específico cuando se le anima a hacerlo, y cómo se compara con su nivel de actividad de ayer. |
| 8 | "está más quietico/a de lo normal" | Puede ser reposo esperado tras la cirugía, dolor que limita el movimiento, o un cambio de comportamiento que preocupa al cuidador sin causa clara. | Preguntar si el niño evita moverse por molestia/dolor o si simplemente está descansando tranquilo sin quejas asociadas. |
| 9 | "amaneció torcido/a" | Puede referirse a mal genio/irritabilidad, a una postura corporal anómala, o a malestar físico general al despertar. | Preguntar si "torcido" se refiere al ánimo (irritable, de mal humor) o a cómo se mueve o se para físicamente, y pedir que lo describa. |
| 10 | "tiene la carita rara" | Observación subjetiva de expresión facial que puede indicar dolor, malestar, cansancio, o simplemente percepción del cuidador sin un signo objetivo claro. | Preguntar qué le hace ver la cara "rara": si hace gestos de dolor, si está pálido, si tiene los ojos hinchados o algo puntual que pueda describir. |
| 11 | "está caliente" | Puede significar fiebre medida con termómetro, sensación de calor al tacto sin medición, o simplemente temperatura ambiente/abrigo excesivo. | Preguntar si le ha tomado la temperatura con termómetro y qué valor marcó, o si es solo una sensación al tocarlo sin medición. |
| 12 | "le da vueltas la cabeza" | Puede indicar mareo real, desequilibrio al caminar, o una expresión usada de forma más general para "confusión" o "cansancio". | Preguntar si el mareo ocurre al pararse, al acostarse, o en cualquier posición, y si ha afectado su equilibrio al caminar. |
| 13 | "tiene el estómago revuelto" | Puede indicar náusea, molestia digestiva leve, falta de apetito, o simplemente una sensación imprecisa sin síntoma claro asociado. | Preguntar si ha tenido ganas de vomitar, si ha vomitado, o si simplemente no ha querido comer, distinguiendo cada posibilidad. |
| 14 | "no ha querido ni probar bocado" | Puede reflejar falta de apetito esperada tras cirugía, náusea, dolor al tragar, o simplemente preferencia/mal genio momentáneo. | Preguntar desde cuándo no come, si ha tomado líquidos, y si rechaza la comida por dolor, náusea, o sin razón aparente. |
| 15 | "está muy sentido/a" | Ambiguo entre malestar emocional (llanto, apego, irritabilidad) y una manera coloquial de decir que "algo le duele" en cierta zona. | Preguntar si se refiere al estado de ánimo del niño o a que algo específico le duele o le molesta al tocarlo. |
| 16 | "tiene mal cuerpo" | Expresión muy general que puede cubrir malestar físico difuso, dolor, fiebre, o simplemente "no se ve bien" sin un signo concreto. | Pedir que describa con más detalle qué observa: dolor, fiebre, cansancio, algo en la piel, o cualquier signo puntual. |
| 17 | "está bajoneado/a" | Puede indicar ánimo decaído, tristeza, o confundirse con cansancio físico postoperatorio normal. | Preguntar si se refiere al ánimo/estado emocional del niño o a que lo nota físicamente cansado o sin fuerzas. |
| 18 | "amaneció rendido/a" | Puede ser cansancio esperado por la recuperación, somnolencia excesiva que preocupa, o simplemente que durmió poco la noche anterior. | Preguntar cuántas horas durmió, si se despierta con facilidad cuando lo llaman, y si este cansancio es distinto al de los días anteriores. |
| 19 | "le duele por ahí" (señalando sin precisar) | Ubicación del dolor no verbalizada con claridad; puede referirse a la zona de la herida o a un área distinta no relacionada con la cirugía. | Pedir que confirme si el dolor está en la zona de la cirugía o en otra parte del cuerpo, y que intente describir la ubicación con más precisión. |
| 20 | "no se le quita lo llorón/llorona" | Puede indicar dolor persistente, malestar general, ansiedad/miedo asociado al procedimiento, o simplemente cansancio y mal genio de un niño pequeño. | Preguntar si el llanto ocurre al moverse, al tocar alguna zona, o si parece sin causa física identificable, y desde cuándo persiste. |
| 21 | "está como ausente" | Puede indicar somnolencia esperada, falta de respuesta preocupante, o simplemente que el niño está callado/tímido en la llamada o presencia de terceros. | Preguntar si el niño responde a su nombre, sigue instrucciones simples, y si reconoce a las personas alrededor con normalidad. |
| 22 | "tiene molestias" | Término genérico que puede cubrir dolor, incomodidad leve, picazón, o cualquier signo menor sin especificar cuál. | Pedir que especifique en qué consisten las "molestias": dolor, picazón, ardor, incomodidad al moverse, u otra cosa. |
| 23 | "quedó fue mal" | Expresión coloquial genérica que puede abarcar desde malestar leve esperado hasta una preocupación seria, sin indicar cuál. | Preguntar explícitamente qué cambió respecto a antes de la cirugía o respecto a horas previas, y pedir ejemplos concretos de lo que "mal" significa aquí. |
| 24 | "está achantado/a" | Puede significar decaimiento físico, timidez/retraimiento emocional, o simplemente estar callado por cansancio. | Preguntar si el niño está así por dolor/cansancio físico o por una reacción emocional (miedo, vergüenza, tristeza). |
| 25 | "tiene guayabo" (sin mencionar anestesia, usado de forma general) | Expresión coloquial que fuera de contexto postoperatorio suele asociarse a resaca; en este contexto puede significar cualquier malestar general post-procedimiento. | Confirmar a qué se refiere exactamente en este contexto (mareo, náusea, cansancio) antes de registrar cualquier observación, sin asumir el significado coloquial habitual. |

---

## Notas de implementación (no normativas, solo guía de uso del fixture)

- Este glosario es un punto de partida para pruebas de `CON-003` (manejo de ambigüedad colombiana); no pretende ser exhaustivo ni representar la variedad dialectal completa del país.
- Cualquier expresión nueva que aparezca en pruebas reales debe agregarse siguiendo el mismo patrón de tres columnas y la misma regla transversal: nunca mapear directo a síntoma sin aclaración.
- El uso de este glosario en el `InterviewAgent` debe registrar tanto la expresión original como la aclaración obtenida, para mantener trazabilidad del razonamiento (contrato de citas/observaciones de `spec.md`).
