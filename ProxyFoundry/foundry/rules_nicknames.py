"""Display-only self-name substitutions, before structural text fitting."""
import copy
import re

VERSION=1


def face_nicknames(card, saved_faces=(), staged=None):
    faces=card.get('card_faces') or [card]
    result={f['name']:str(f.get('flavor_name',card.get('flavor_name')) or '').strip() for f in faces if f.get('name')}
    for saved in saved_faces:
        face=faces[min(int(saved.get('index',0)),len(faces)-1)]
        overrides=saved.get('semanticOverrides') or {}
        if face.get('name') and 'nickname' in overrides:result[face['name']]=str(overrides['nickname'] or '').strip()
    for name,values in (staged or {}).items():
        if name in result and 'nickname' in values:result[name]=str(values['nickname'] or '').strip()
    return result


def short_names(entry):
    name=entry['name']
    if ',' in name:return [name.split(',',1)[0].strip()]
    types=entry.get('types') or re.split(r'\s+[—–-]\s+',entry.get('type_line',''),maxsplit=1)[0].split()
    if 'Planeswalker' not in types:return []
    subtypes=entry.get('subtypes')
    if subtypes is None:
        parts=re.split(r'\s+[—–-]\s+',entry.get('type_line',''),maxsplit=1)
        subtypes=parts[1].split() if len(parts)>1 else []
    return [s for s in subtypes if re.search(r'(?<!\w)'+re.escape(s)+r'(?!\w)',name)]


class RulesNames:
    def __init__(self, entries):
        self.matches={};self.active=False
        # All full face names participate, including unrenamed sibling faces.
        # They protect their own names from another face's shorter alias.
        for entry in entries:
            name=entry['name'];nick=str(entry.get('nickname') or '').strip()
            self.active|=bool(nick)
            replacement=(nick.split(',',1)[0].strip() if ',' not in name and ',' in nick else nick) if nick else None
            self.matches[name]=(replacement,False)
        for entry in entries:
            nick=str(entry.get('nickname') or '').strip()
            if not nick:continue
            for short in short_names(entry):
                # Entries put the current face first. An ambiguous shared short
                # name therefore refers to that face, while full names still win.
                self.matches.setdefault(short,(nick.split(',',1)[0].strip(),True))
        # Raw card edits can contain already-formatted rules. Consume complete
        # nickname strings as literals so names embedded in them stay unchanged.
        for entry in entries:
            nick=str(entry.get('nickname') or '').strip()
            if nick:
                self.matches.setdefault(nick,(None,False))
                self.matches.setdefault(nick.split(',',1)[0].strip(),(None,False))
        choices=sorted((n for n in self.matches if n),key=len,reverse=True)
        self.pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(n) for n in choices)+r')(?!\w)') if self.active and choices else None

    def format(self, text):
        if not self.pattern or not text:return text
        def replace(match):
            original=match.group();replacement,short=self.matches[original]
            if replacement is None:return original
            before=text[:match.start()]
            if before.rfind('{')>before.rfind('}'):return original
            tail=text[match.end():]
            # A short alias followed by a different title is another card name,
            # e.g. Avacyn, Angel of Hope or Tezzeret the Schemer.
            continuation=r'(?:,[ \t]+|[ \t]+(?:the[ \t]+|of[ \t]+(?:the[ \t]+)?)?)[A-Z][\w’\'-]*'
            if short and re.match(continuation,tail):return original
            # Also protect a full single-word name within a longer named card.
            if re.search(r'\bnamed[ \t]+$',before) and re.match(continuation,tail):return original
            named=re.search(r'\bnamed[ \t]+([^.;\n]*)$',before)
            if named:
                prefix=named[1].strip(' \t"\'')
                clause_ended=re.search(r',[ \t]+[a-z]',prefix)
                next_name=re.search(r'(?:^|[ \t])(?:and|or|and/or)[ \t]*$',prefix)
                if prefix and not clause_ended and not next_name:return original
            return replacement
        # Callback replacements are literal; inserted text is never rescanned.
        return self.pattern.sub(replace,text)

    def display_face(self, face):
        result=copy.deepcopy(face)
        result['oracle_text']=self.format(result.get('oracle_text',''))
        return result


def for_semantic(sem, card=None, nicknames=None):
    entries=[{**sem,'nickname':sem.get('nickname','')}]
    for face in (card or {}).get('card_faces',[]):
        if face.get('name')==sem['name']:continue
        entries.append({**face,'nickname':(nicknames or {}).get(face['name'],face.get('flavor_name',''))})
    for key in ('flip_face','prepared_spell'):
        nested=sem.get(key)
        if nested and not any(e['name']==nested['name'] for e in entries):entries.append(nested)
    return RulesNames(entries)


def apply_semantic(sem, card=None, nicknames=None):
    formatter=for_semantic(sem,card,nicknames)
    if formatter.active and not sem.get('_nicknameRulesApplied'):
        sem['oracle_text']=formatter.format(sem.get('oracle_text',''))
        for key in ('flip_face','prepared_spell'):
            if sem.get(key):sem[key]['oracle_text']=formatter.format(sem[key].get('oracle_text',''))
        sem['_nicknameRulesApplied']=True
    return formatter


def format_raw_rules(data, formatter):
    for key,field in data.get('text',{}).items():
        if not isinstance(field,dict) or not re.fullmatch(r'rules\d*|ability\d+|level\d+c|reminder',key):continue
        rules,marker,flavor=str(field.get('text') or '').partition('{flavor}')
        field['text']=formatter.format(rules)+marker+flavor
