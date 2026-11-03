"""Every text the server produces for people, in Spanish (Spain) and English.

Machine fields (class codes, kinds, option codes, check ids, numbers) never go through here. The language comes from a
``lang`` argument or, per request, from the ``X-Lang`` header; a context variable carries it down to the renderers."""
from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar

LANGS = ("es", "en")
_lang: ContextVar[str | None] = ContextVar("drucker_lang", default=None)


def norm(value):
    v = str(value or "").strip().lower()[:2]
    return v if v in LANGS else None


def explicit():
    """The language asked for in this call, or None when nobody asked."""
    return _lang.get()


def cur():
    return _lang.get() or "en"


@contextmanager
def using(lang):
    token = _lang.set(norm(lang) or _lang.get())
    try:
        yield
    finally:
        _lang.reset(token)


def localized(fn):
    """Let a function take ``lang=`` and render its texts in that language."""
    @functools.wraps(fn)
    def wrapper(*args, lang=None, **kwargs):
        with using(lang):
            return fn(*args, **kwargs)
    return wrapper


def tr(key, lang=None, **p):
    entry = M.get(key)
    if entry is None:
        return key
    lang = norm(lang) or cur()
    text = entry[1] if lang == "es" else entry[0]
    return text.format(**p)


M = {
    # ---- item kinds (history summaries)
    "kind.scope": ("scope", "alcance"), "kind.milestone": ("milestone", "hito"), "kind.material": ("material", "material"),
    "kind.decision": ("decision", "decisión"), "kind.payment": ("payment", "cobro"), "kind.assumption": ("assumption", "supuesto"),
    "kind.question": ("question", "pregunta"),
    "status.open": ("open", "abierto"), "status.fixed": ("fixed", "corregido"), "status.wontfix": ("won't fix", "no se corrige"),
    # ---- history
    "h.eng_created": ("Engagement created: {name}", "Encargo creado: {name}"),
    "h.eng_updated": ("Engagement updated: {fields}", "Encargo actualizado: {fields}"),
    "h.item_added": ("{kind} added: {title}", "{kind}: añadido «{title}»"),
    "h.item_updated": ("{kind} updated: {title}", "{kind}: actualizado «{title}»"),
    "h.item_removed": ("{kind} removed: {title}", "{kind}: eliminado «{title}»"),
    "h.del_added": ("deliverable added: {name}", "entregable añadido: {name}"),
    "h.del_renamed": ("deliverable renamed: {name}", "entregable renombrado: {name}"),
    "h.version_added": ("{name}: version {n} added", "{name}: versión {n} añadida"),
    "h.comment_added": ("{name} v{n}: comment added", "{name} v{n}: comentario añadido"),
    "h.comment_status": ("{name} v{n}: comment {status}", "{name} v{n}: comentario {status}"),
    "h.marked": ("{name}: version {n} marked to deliver", "{name}: versión {n} marcada para entregar"),
    "h.pkg_ready": ("{name} v{n}: package ready", "{name} v{n}: paquete listo"),
    "h.pkg_not_ready": ("{name} v{n}: package not ready", "{name} v{n}: paquete no listo"),
    # ---- errors
    "e.not_found_eng": ("Engagement {id!r} not found", "No existe el encargo {id!r}"),
    "e.not_found_del": ("Deliverable {id!r} not found", "No existe el entregable {id!r}"),
    "e.not_found_ver": ("Version {id!r} not found", "No existe la versión {id!r}"),
    "e.not_found_ver_in": ("Version {id!r} not found in this deliverable", "No existe la versión {id!r} en este entregable"),
    "e.not_found_com": ("Comment {id!r} not found", "No existe el comentario {id!r}"),
    "e.not_found_item": ("{kind} {id!r} not found in this engagement", "No existe {kind} {id!r} en este encargo"),
    "e.not_found_item2": ("Item {id!r} not found in this engagement", "No existe el elemento {id!r} en este encargo"),
    "e.items_object": ("items must be an object {{kind: [..]}}", "items debe ser un objeto {{tipo: [..]}}"),
    "e.unknown_kind": ("Unknown item kind {kind!r}; use one of {kinds}", "Tipo de elemento desconocido {kind!r}; usa uno de {kinds}"),
    "e.denylist_list": ("denylist must be a list of strings", "denylist debe ser una lista de textos"),
    "e.use_md_html": ("Use .md or .html", "Usa .md o .html"),
    "e.no_zip": ("No zip for that package (not ready, or never built)", "Ese paquete no tiene zip (no está listo o no se construyó)"),
    "e.entry": ("{role}: each file is a path or an object {{path, sha256?, format?}}", "{role}: cada archivo es una ruta o un objeto {{path, sha256?, format?}}"),
    "e.lang": ("lang must be es or en", "lang debe ser es o en"),
    "e.format_md_html": ("format must be md or html", "format debe ser md o html"),
    "e.refused_names": ("Refused: client-facing material would contain internal names: {terms}",
                        "Rechazado: el material para el cliente contendría nombres internos: {terms}"),
    "e.file_ref_type": ("file_ref must be a path, a URL or an object {{kind, ref}}", "file_ref debe ser una ruta, una URL o un objeto {{kind, ref}}"),
    "e.file_ref_kind": ("file_ref.kind must be path, url or atlas", "file_ref.kind debe ser path, url o atlas"),
    "e.file_ref_ref": ("file_ref.ref is required", "file_ref.ref es obligatorio"),
    "e.anchor": ("anchor must be {{kind: page|region|time|object, value}}", "anchor debe ser {{kind: page|region|time|object, value}}"),
    "e.anchor_time": ("time anchor needs numeric start <= end (seconds)", "El ancla de tiempo necesita start <= end numéricos (segundos)"),
    "e.name_required": ("name is required", "name es obligatorio"),
    "e.sha_hex": ("sha256 must be 64 hex characters", "sha256 debe tener 64 caracteres hexadecimales"),
    "e.sha_mismatch": ("Declared sha256 does not match the file on disk", "El sha256 declarado no coincide con el archivo en disco"),
    "e.text_required": ("text is required", "text es obligatorio"),
    "e.status_values": ("status must be open, fixed or wontfix", "status debe ser open, fixed o wontfix"),
    "e.fixed_in_required": ("fixed_in (version number) is required when status is fixed", "fixed_in (número de versión) es obligatorio si status es fixed"),
    "e.fixed_later": ("A comment can only be fixed in a later version than the one it is about", "Un comentario solo se corrige en una versión posterior a la que comenta"),
    "e.scope_items": ("Scope items must be text or objects with a text field", "Los elementos del alcance deben ser texto u objetos con un campo text"),
    "e.scope_type": ("Scope must be text or a list of items", "El alcance debe ser texto o una lista de elementos"),
    "e.request_mode": ("request_mode must be delta or full", "request_mode debe ser delta o full"),
    "e.no_request": ("The new request has no items", "La petición nueva no tiene elementos"),
    "e.no_baseline": ("Give the agreement or the initial request to compare against", "Indica el acuerdo o la petición inicial con los que comparar"),
    "e.rate": ("hourly_rate needs numeric min <= max", "hourly_rate necesita min y max numéricos, con min <= max"),
    "e.hours": ("hours must be a number or {{min, max}} with min <= max", "hours debe ser un número o {{min, max}} con min <= max"),
    "e.give_ids": ("Give deliverable_id or engagement_id", "Indica deliverable_id o engagement_id"),
    "e.unknown_tool": ("Unknown tool {name!r}", "Herramienta desconocida {name!r}"),
    "e.args_object": ("arguments must be an object", "arguments debe ser un objeto"),
    "e.required": ("{name} is required", "{name} es obligatorio"),
    "e.unknown_args": ("Unknown argument(s): {names}", "Argumento(s) desconocido(s): {names}"),
    "e.cross_origin": ("cross-origin request refused", "Petición de otro origen rechazada"),
    "e.bad_token": ("missing or invalid token", "Falta el token o no es válido"),
    "e.budget": ("budget_min must not be above budget_max", "budget_min no puede ser mayor que budget_max"),
    "pyd.missing": ("Field required", "Campo obligatorio"),
    "pyd.literal_error": ("Value not allowed", "Valor no permitido"),
    "pyd.string_too_short": ("Must not be empty", "No puede estar vacío"),
    "pyd.extra_forbidden": ("Unknown field", "Campo desconocido"),
    "pyd.other": ("Invalid value", "Valor no válido"),
    # ---- scope
    "s.same": ("Same as an agreed item.", "Igual que un punto acordado."),
    "s.qty": ("Looks like the agreed item but the number changes ({old} -> {new}).",
              "Parece el punto acordado, pero cambia la cifra ({old} -> {new})."),
    "s.negation": ("Similar to an agreed item but it flips an exclusion or negation.",
                   "Parecido a un punto acordado, pero invierte una exclusión o una negación."),
    "s.included": ("Wording differs but everything it asks is in an agreed item.",
                   "Está redactado distinto, pero todo lo que pide ya está en un punto acordado."),
    "s.overlap": ("Overlaps an agreed item but asks for more or something different; not certain.",
                  "Se solapa con un punto acordado, pero pide más o algo distinto; no es seguro."),
    "s.added": ("No agreed item covers it.", "Ningún punto acordado lo cubre."),
    "s.dropped": ("It was in the initial request ({text!r}) and is not in the agreement.",
                  "Estaba en la petición inicial ({text!r}) y no está en el acuerdo."),
    "s.removed": ("Agreed, but the new request does not mention it.", "Está acordado, pero la petición nueva no lo menciona."),
    "s.removal": ("Work already done on it is not recoverable; any saving applies only to work not yet started. Confirm status before crediting.",
                  "El trabajo ya hecho no se recupera; el ahorro solo afecta a lo que no se ha empezado. Confirma el estado antes de abonar nada."),
    "s.already": ("Already part of the agreement; no extra work to price.", "Ya forma parte del acuerdo; no hay trabajo extra que presupuestar."),
    "s.nochange": ("No change.", "Sin cambios."),
    "s.eff_qty": ("Quantity changes from {a} to {b}: about {delta} more unit(s) at {lo}-{hi} h each; the process itself does not change.",
                  "La cantidad pasa de {a} a {b}: unas {delta} unidad(es) más, a {lo}-{hi} h cada una; el proceso no cambia."),
    "s.eff_pipe": ("Changes how the work is produced, not just how it looks: it touches an earlier stage, so everything after it is redone and revalidated{dels}{ms}.",
                   "Cambia cómo se produce el trabajo, no solo cómo se ve: toca una fase anterior, así que todo lo posterior se rehace y se revalida{dels}{ms}."),
    "s.pipe_dels": (" (deliverables: {v})", " (entregables: {v})"),
    "s.pipe_ms": (" (open milestones: {v})", " (hitos abiertos: {v})"),
    "s.eff_fmt1": ("Output format change on {n} deliverable(s){dels}; it touches only the last stage, no earlier milestone is reopened.",
                   "Cambio de formato de salida en {n} entregable(s){dels}; solo afecta a la última fase, no se reabre ningún hito anterior."),
    "s.eff_fmtn": ("Output format change repeated across {n} deliverables ({dels}); still last-stage work only.",
                   "Cambio de formato repetido en {n} entregables ({dels}); sigue siendo trabajo de la última fase."),
    "s.fmt_dels": (" ({v})", " ({v})"),
    "s.eff_content": ("It extends an agreed item beyond what is written{touch}. Range from the default band; refine once it is specified.",
                      "Amplía un punto acordado más allá de lo escrito{touch}. Rango de la banda por defecto; afínalo cuando esté especificado."),
    "s.touch": ("; it touches {v}", "; afecta a {v}"),
    "s.eff_unest": ("New work with nothing like it in the agreement{touch}. Not estimated: it needs a specification first, and a default band would understate a new product.",
                    "Trabajo nuevo sin nada parecido en el acuerdo{touch}. Sin estimar: antes necesita una especificación, y una banda por defecto infravaloraría un producto nuevo."),
    "s.eff_given": ("Hours given by you: {rng}.", "Horas indicadas por ti: {rng}."),
    "s.min_zero": (" Minimum is zero because it may already be covered once clarified.",
                   " El mínimo es cero porque, una vez aclarado, puede que ya esté cubierto."),
    "s.o_include": ("Include in the current scope", "Incluir en el alcance actual"),
    "s.o_include_sum": ("Absorb {rng} inside the agreed price and dates.", "Asumir {rng} dentro del precio y las fechas acordados."),
    "s.o_order": ("Change order with a range", "Orden de cambio con rango"),
    "s.o_order_sum": ("Agree in writing an extra {rng}{money}; confirm whether milestones move.",
                      "Acordar por escrito {rng} extra{money}; confirmar si se mueven los hitos."),
    "s.o_defer": ("Defer to a later phase", "Aplazar a una fase posterior"),
    "s.o_defer_sum": ("Keep the current scope and dates; schedule this separately after delivery.",
                      "Mantener el alcance y las fechas actuales; planificarlo aparte después de la entrega."),
    "s.o_specify": ("Specify and estimate separately", "Especificar y estimar aparte"),
    "s.o_specify_sum": ("Write down what it must do, estimate it as its own piece and agree it in writing before any work.",
                        "Escribir qué debe hacer, estimarlo como pieza propia y acordarlo por escrito antes de empezar."),
    "s.method": ("Deterministic token and sequence similarity. Effort ranges follow editable rule bands and the deliverables each item touches; they are not prices and not a quote. Uncertain matches are marked ambiguous, never forced. New items with no counterpart in the agreement are not given hours: they need a specification.",
                 "Similitud determinista de palabras y secuencia. Los rangos de esfuerzo siguen bandas editables y los entregables que toca cada punto; no son precios ni presupuesto. Las coincidencias dudosas se marcan como ambiguas, nunca se fuerzan. Los puntos nuevos sin nada parecido en el acuerdo no llevan horas: necesitan una especificación."),
    # ---- review
    "r.stale": ("About v{v}; {span} {verb}. Check whether it already addresses this.", "Sobre v{v}; {span} {verb}. Comprueba si ya lo resuelve."),
    "r.span1": ("v{a}", "v{a}"), "r.spann": ("v{a} to v{b}", "de v{a} a v{b}"),
    "r.verb1": ("is newer and differs", "es más nueva y distinta"), "r.verbn": ("are newer and differ", "son más nuevas y distintas"),
    "r.identical": ("v{latest} has identical content to v{v}: the feedback still applies.", "v{latest} tiene el mismo contenido que v{v}: el comentario sigue vigente."),
    "r.fixed": ("Fixed in v{n}.", "Corregido en v{n}."),
    "r.wontfix": ("Closed as won't fix.", "Cerrado como no se corrige."),
    "r.w_none": ("No versions yet.", "Aún no hay versiones."),
    "r.w_unselected": ("No version selected to deliver.", "No hay versión elegida para entregar."),
    "r.w_notlatest": ("The version to deliver (v{n}) is not the latest (v{latest}).", "La versión para entregar (v{n}) no es la última (v{latest})."),
    "r.w_open": ("{c} open comment(s) on v{n}.", "{c} comentario(s) abierto(s) en v{n}."),
    "r.w_old": ("Open feedback about older versions still needs a decision.", "Hay comentarios abiertos de versiones anteriores que aún necesitan una decisión."),
    # ---- package
    "p.role.editable": ("editable", "editable"), "p.role.export": ("export", "exportación"), "p.role.example": ("example", "ejemplo"),
    "p.has_editable": ("At least one editable file", "Al menos un archivo editable"),
    "p.has_editable_d": ("Add the source/editable files so the work can be reproduced.", "Añade los archivos fuente o editables para poder reproducir el trabajo."),
    "p.empty": ("(empty)", "(vacío)"),
    "p.not_local": ("Not a local file: cannot verify existence or hash. Give a local path.", "No es un archivo local: no se puede comprobar si existe ni su hash. Indica una ruta local."),
    "p.not_found": ("File not found.", "No se encuentra el archivo."),
    "p.exists": ("File exists.", "El archivo existe."),
    "p.hash": ("hash: {name}", "hash: {name}"),
    "p.hash_ok": ("Hash matches.", "El hash coincide."),
    "p.hash_bad": ("Declared {a}..., file is {b}...", "Declarado {a}..., el archivo es {b}..."),
    "p.opens": ("opens: {name}", "se abre: {name}"),
    "p.version_hash": ("Version file matches recorded hash ({name})", "El archivo de la versión coincide con el hash registrado ({name})"),
    "p.version_hash_ok": ("Recorded hash matches.", "El hash registrado coincide."),
    "p.version_hash_bad": ("The file changed after the version was recorded, or is missing.", "El archivo cambió tras registrar la versión, o falta."),
    "p.source": ("Data source: {name}", "Fuente de datos: {name}"), "p.no_name": ("(no name)", "(sin nombre)"),
    "p.source_ok": ("Authorised.", "Autorizada."),
    "p.source_bad": ("Not authorised (set authorised: true only once the owner of the data has agreed).", "Sin autorizar (pon authorised: true solo cuando el dueño de los datos lo haya aceptado)."),
    "p.instr": ("Instructions present", "Instrucciones presentes"),
    "p.instr_d": ("Write how to open, rebuild and use the files.", "Escribe cómo abrir, reconstruir y usar los archivos."),
    "p.limits": ("Limitations declared", "Límites declarados"),
    "p.limits_d": ("State the real limitations (write \"none known\" only if true).", "Indica los límites reales (escribe «ninguno conocido» solo si es verdad)."),
    "p.zip": ("Zip re-opens and matches the manifest", "El zip se reabre y coincide con el manifiesto"),
    "p.zip_corrupt": ("zip is corrupt", "el zip está dañado"),
    "p.zip_differs": ("{name} differs from the manifest", "{name} no coincide con el manifiesto"),
    "p.zip_missing": ("{name} missing", "falta {name}"),
    "p.limitations_title": ("Limitations", "Límites"),
    "v.cannot_read": ("cannot read: {why}", "no se puede leer: {why}"),
    "v.no_validator": ("no validator for this format; existence and hash only", "no hay validador para este formato; solo existencia y hash"),
    "v.empty": ("file is empty", "el archivo está vacío"),
    "v.zip_corrupt": ("corrupt member {name}", "miembro dañado {name}"),
    "v.zip_members": ("{n} member(s)", "{n} miembro(s)"), "v.zip_empty": ("zip has no members", "el zip no tiene miembros"),
    "v.json_ok": ("parses as JSON", "se lee como JSON"),
    "v.csv_head": ("no header row", "no hay fila de cabecera"),
    "v.csv_width": ("rows with a different number of columns than the header", "hay filas con distinto número de columnas que la cabecera"),
    "v.csv_ok": ("{rows} data row(s), {cols} column(s)", "{rows} fila(s) de datos, {cols} columna(s)"),
    "v.pdf_head": ("missing %PDF- header", "falta la cabecera %PDF-"),
    "v.pdf_ok": ("PDF header and end marker found", "cabecera y marca final de PDF encontradas"),
    "v.pdf_trunc": ("missing %%EOF end marker (truncated?)", "falta la marca final %%EOF (¿truncado?)"),
    "v.png_bad": ("not a PNG (signature/IHDR)", "no es un PNG (firma/IHDR)"),
    "v.png_zero": ("zero dimensions", "dimensiones nulas"),
    "v.png_trunc": ("missing IEND (truncated?)", "falta IEND (¿truncado?)"),
    "v.glb_magic": ("not a GLB (magic)", "no es un GLB (número mágico)"),
    "v.glb_header": ("GLB header says version {v}, {len} bytes; file has {size}", "La cabecera GLB dice versión {v}, {len} bytes; el archivo tiene {size}"),
    "v.glb_chunk": ("first chunk is not JSON", "el primer bloque no es JSON"),
    "v.glb_ok": ("GLB 2.0, JSON chunk parses", "GLB 2.0, el bloque JSON se lee"),
    "v.stl_ascii": ("ASCII STL with facets", "STL ASCII con caras"),
    "v.stl_bin": ("binary STL, {n} triangle(s)", "STL binario, {n} triángulo(s)"),
    "v.stl_bad": ("neither a complete ASCII STL nor a binary STL with a consistent size", "ni es un STL ASCII completo ni un STL binario con tamaño coherente"),
    "v.open_fail": ("does not open as {fmt}: {why}", "no se abre como {fmt}: {why}"),
    "v.no_validator_short": ("no validator", "sin validador"),
}


def pyd(kind):
    return tr("pyd." + kind) if ("pyd." + kind) in M else tr("pyd.other")
