./.venv/bin/python - <<'PY'
import asyncio, json, sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path.cwd()))
import backend.opencode as opencode
opencode.MESSAGE_PAGE_SIZE=1
from backend.api import create_app
questions=[
 "Over the last month the operators have written notes about wells that sound or behave wrong. Which of those wells haven't had a repair since? Rank the 10 most likely to need a repair in the next 90 days, other than a spill clean-up, and quote the notes as evidence.",
 "Which three would you send a crew to first this week, and why?",
]
async def main():
    app=create_app(Path('data/well_copilot.db').resolve())
    session_id=None
    path=Path('context/final_answers.md')
    doc=json.loads(path.read_text(encoding='utf-8'))
    existing={(x.get('question_id'),x.get('turn')) for x in doc['answers']}
    if any(('Q7',n) in existing for n in (1,2)):
        raise RuntimeError('Q7 answer already present; refusing duplicate run')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://copilot',timeout=360) as client:
        for number,question in enumerate(questions,1):
            payload={'user_id':'U-301','question':question,'dataset_id':'test'}
            if session_id:
                payload['session_id']=session_id
            response=await client.post('/chat',json=payload)
            if response.status_code != 200:
                print(f'HTTP failure Q7 turn {number}:',response.status_code,response.text)
                return
            data=response.json()
            session_id=data['session_id']
            doc['answers'].append({'question_id':'Q7','turn':number,'user':'Robert Hayes','question':question,'response':data})
            path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'Q7 turn {number} saved; session={session_id}; visual={data["visual"].get("type") if data.get("visual") else None}')
            print('answer:',data['answer'])
            print('citations:',data['citations'])
asyncio.run(main())
PY