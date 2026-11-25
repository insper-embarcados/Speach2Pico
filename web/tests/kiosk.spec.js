import {test, expect} from '@playwright/test';

test.beforeEach(async ({request}) => {
  await request.post('/api/new', {headers:{'X-Kiosk-Request':'1'}});
});

test('voice entry, game while generating, explicit execute, repeat and modify', async ({page}) => {
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('DEMO',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Executar',exact:true})).toBeDisabled();
  await page.screenshot({path:'test-results/kiosk-portrait.png',fullPage:true});
  await page.getByRole('button',{name:'Falar novo código'}).click();
  await expect(page.getByRole('status',{name:'Aguardando a API'})).toBeVisible();
  await page.getByRole('button',{name:'Apertar cintos'}).click();
  await page.getByRole('button',{name:'Girar manivela'}).click();
  await expect(page.getByRole('button',{name:'Cintos apertados'})).toBeVisible();
  await page.screenshot({path:'test-results/kiosk-generating.png',fullPage:true});
  await expect(page.getByRole('button',{name:'Executar',exact:true})).toBeEnabled({timeout:15000});
  const before=await (await page.request.get('/api/status')).json();
  expect(before.phase).toBe('ready');
  await page.screenshot({path:'test-results/kiosk-ready.png',fullPage:true});
  await page.getByRole('button',{name:'Executar',exact:true}).click();
  await expect(page.getByRole('status',{name:'Executando no Pololu'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Repetir',exact:true})).toBeEnabled({timeout:8000});
  const after=await (await page.request.get('/api/status')).json();
  expect(after.completed).toBe(before.completed+1);
  await page.getByRole('button',{name:'Modificar',exact:true}).click();
  await expect(page.getByRole('status',{name:'Aguardando a API'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Executar',exact:true})).toBeEnabled({timeout:15000});
  expect(errors).toEqual([]);
});

test('Wi-Fi keyboard and Bluetooth panel', async ({page}) => {
  await page.goto('/');
  await expect(page.getByText('DEMO',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Wi-Fi',exact:true}).click();
  await page.getByRole('button',{name:/Laboratório · exemplo/}).click();
  await expect(page.getByRole('textbox',{name:'Rede',exact:true})).toHaveValue('Laboratório · exemplo');
  await page.getByRole('button',{name:'Teclado da senha'}).click();
  await page.getByRole('button',{name:'a',exact:true}).click();
  await page.getByRole('button',{name:'1',exact:true}).click();
  await page.getByRole('button',{name:'Concluir teclado'}).click();
  await expect(page.getByLabel('Senha',{exact:true})).toHaveValue('a1');
  await expect(page.getByRole('button',{name:'Conectar',exact:true})).toBeDisabled();
  await page.screenshot({path:'test-results/kiosk-wifi.png',fullPage:true});
  await page.getByRole('button',{name:'Fechar painel'}).click();
  await page.getByRole('button',{name:/Bluetooth:/}).click();
  await expect(page.getByText('Simulado',{exact:true})).toBeVisible();
  await expect(page.getByText('1 s',{exact:true})).toBeVisible();
});

test('all kiosk buttons fit portrait, landscape and small phone without scrolling', async ({page}) => {
  for(const [width,height] of [[720,1280],[1280,720],[360,800]]){
    await page.setViewportSize({width,height});
    await page.goto('/');
    await expect(page.getByRole('button',{name:'Novo código',exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight)).toBe(true);
    await page.screenshot({path:`test-results/kiosk-${width}.png`,fullPage:true});
  }
});
