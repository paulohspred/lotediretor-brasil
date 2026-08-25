import {Module} from '@nestjs/common';
import {AppModule} from './app.module';
import {ControlV20AdminController,ControlV20InternalController,ControlV20PublicController} from './v20-admin.controller';

@Module({imports:[AppModule],controllers:[ControlV20AdminController,ControlV20InternalController,ControlV20PublicController]})
export class ControlV20Module{}
