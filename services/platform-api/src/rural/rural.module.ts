import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {RuralController} from './rural.controller';
import {RuralV20Controller} from './rural-v20.controller';
@Module({imports:[CoreModule],controllers:[RuralController,RuralV20Controller]})
export class RuralModule{}
