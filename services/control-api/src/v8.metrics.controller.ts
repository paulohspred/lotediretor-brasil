import {Controller,Get,Res} from '@nestjs/common';
import {Pool} from 'pg';

const pool=new Pool({connectionString:process.env.CONTROL_DATABASE_URL});
const started=Date.now();

@Controller()
export class ControlMetricsController{
  @Get('metrics')
  async metrics(@Res() res:any){
    let db=1;
    try{await pool.query('select 1')}catch{db=0}
    const uptime=Math.max(0,(Date.now()-started)/1000);
    const body=[
      '# HELP lotediretor_service_up Service process/database readiness.',
      '# TYPE lotediretor_service_up gauge',
      `lotediretor_service_up{service="control-api"} ${db}`,
      '# HELP lotediretor_process_uptime_seconds Process uptime in seconds.',
      '# TYPE lotediretor_process_uptime_seconds gauge',
      `lotediretor_process_uptime_seconds{service="control-api"} ${uptime.toFixed(3)}`,
      '# HELP lotediretor_build_info Static build information.',
      '# TYPE lotediretor_build_info gauge',
      'lotediretor_build_info{service="control-api",version="19.0.0-rc.3"} 1',
      ''
    ].join('\n');
    return res.header('content-type','text/plain; version=0.0.4; charset=utf-8').send(body);
  }
}
