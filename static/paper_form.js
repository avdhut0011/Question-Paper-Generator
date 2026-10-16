(() => {
  const hidden = document.getElementById('blueprint');
  if (!hidden) return;
  let blueprint;
  try { blueprint = JSON.parse(hidden.value); } catch { blueprint = {}; }
  const form = hidden.form;
  const details = document.getElementById('assessment-fields');
  const slots = document.getElementById('slot-fields');
  const definitions = [
    ['title','Assessment name','text'],['academic_year','Academic year','text'],
    ['grade','Grade','text'],['subject','Subject','text'],['board','Board','text'],
    ['duration_minutes','Duration (minutes)','number'],['total_marks','Maximum marks','number'],
    ['num_questions','Number of questions','number']
  ];
  const fields = {};
  function field(parent, labelText, value, choices, numeric) {
    const label = document.createElement('label'); label.textContent = labelText;
    const input = document.createElement(choices ? 'select' : 'input');
    if (choices) choices.forEach(choice => { const option = document.createElement('option'); option.value=choice; option.textContent=choice; input.append(option); });
    else { input.type=numeric?'number':'text'; input.maxLength=100; if(numeric){input.min='1';input.max='1000';input.step='1';} }
    input.value = value ?? ''; input.required = true; label.append(input); parent.append(label); return input;
  }
  definitions.forEach(([key,label,type]) => { fields[key] = field(details,label,blueprint[key],null,type==='number'); });
  const rows = [];
  function addSlot(data={type:'MCQ',marks:1,count:1,chapter:'',difficulty:'easy',bloom:'Understand'}) {
    const card=document.createElement('section'); card.className='card';
    const row=document.createElement('div'); row.className='grid'; card.append(row);
    const controls={};
    controls.chapter=field(row,'Chapter',data.chapter);
    controls.type=field(row,'Question type',data.type,['MCQ','Short Answer','Long Answer','Numerical','True/False']);
    controls.marks=field(row,'Marks per question',data.marks,null,true);
    controls.count=field(row,'Question count',data.count,null,true);
    controls.difficulty=field(row,'Difficulty',data.difficulty,['easy','medium','hard']);
    controls.bloom=field(row,'Thinking skill (Bloom)',data.bloom,['Remember','Understand','Apply','Analyze','Evaluate','Create']);
    const remove=document.createElement('button'); remove.type='button'; remove.className='secondary'; remove.textContent='Remove group';
    const record={card,controls}; rows.push(record); remove.addEventListener('click',()=>{rows.splice(rows.indexOf(record),1);card.remove();sync();});card.append(remove);slots.append(card);sync();
  }
  function sync() {
    const b={}; definitions.forEach(([key,,type])=>{b[key]=type==='number'?Number(fields[key].value):fields[key].value.trim();});
    b.slots=rows.map(({controls})=>Object.fromEntries(Object.entries(controls).map(([key,input])=>[key,['marks','count'].includes(key)?Number(input.value):input.value.trim()])));
    hidden.value=JSON.stringify(b);
    const count=b.slots.reduce((n,s)=>n+s.count,0), marks=b.slots.reduce((n,s)=>n+s.count*s.marks,0);
    document.getElementById('allocation-total').textContent=`Allocated: ${count} questions, ${marks} marks. Target: ${b.num_questions} questions, ${b.total_marks} marks.`;
  }
  (blueprint.slots||[]).forEach(addSlot);
  document.getElementById('add-slot').addEventListener('click',()=>addSlot());
  form.addEventListener('input',sync); form.addEventListener('change',sync); form.addEventListener('submit',sync); sync();
})();
