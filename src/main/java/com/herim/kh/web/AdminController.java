package com.herim.kh.web;

import java.io.FileOutputStream;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.util.List;

import javax.servlet.http.HttpServletResponse;

import org.apache.poi.hssf.usermodel.HSSFCell;
import org.apache.poi.hssf.usermodel.HSSFCellStyle;
import org.apache.poi.hssf.usermodel.HSSFFont;
import org.apache.poi.hssf.usermodel.HSSFRow;
import org.apache.poi.hssf.usermodel.HSSFSheet;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

import com.herim.kh.domain.UserScore;
import com.herim.kh.service.MyConfigService;
import com.herim.kh.service.UserService;

@Controller
@RequestMapping("/admin")
public class AdminController {

	@Autowired
	private UserService userService;
	@Autowired
	private MyConfigService myConfigService;

	/**
	 * 跳转得分情况页面
	 * @param model
	 * @return
	 */
	@RequestMapping("/to-score")
	public String toScore(Model model) {
		List<UserScore> userScores = userService.calculateAllUsersScore(Double.parseDouble(myConfigService.getByKey("sjdf").get(0).getValue()));
		model.addAttribute("userScores", userScores);
		return "score";
	}
	
	@GetMapping("/export-score")
	@ResponseBody
	public void exportScore(HttpServletResponse response) throws Exception {
		HSSFWorkbook workbook = new HSSFWorkbook();
		HSSFSheet sheet = workbook.createSheet("考核评分统计表");
		createTitle(workbook, sheet);
		int rowNum = 1;
		List<UserScore> userScores = userService.calculateAllUsersScore(Double.parseDouble(myConfigService.getByKey("sjdf").get(0).getValue()));
		for(UserScore us : userScores) {
			HSSFRow row = sheet.createRow(rowNum);
			row.createCell(0).setCellValue(us.getUser().getName());
			row.createCell(1).setCellValue(us.getUser().getDept().getName());
			row.createCell(2).setCellValue(us.getFinalScore());
			rowNum++;
		}
		String fileName = "考核评分统计表.xls";
		buildExcelFile(fileName, workbook);
		buildExcelDocument(fileName, workbook, response);
	}
	
	//创建表头
    private void createTitle(HSSFWorkbook workbook,HSSFSheet sheet){
        HSSFRow row = sheet.createRow(0);
        //设置列宽，setColumnWidth的第二个参数要乘以256，这个参数的单位是1/256个字符宽度
        sheet.setColumnWidth(0,12*256);
        sheet.setColumnWidth(1,20*256);
        sheet.setColumnWidth(2,8*256);
        //设置为居中加粗
        HSSFCellStyle style = workbook.createCellStyle();
        HSSFFont font = workbook.createFont();
        font.setBold(true);
        //style.setAlignment(HSSFCellStyle.ALIGN_CENTER);
        style.setFont(font);
        HSSFCell cell;
        cell = row.createCell(0);
        cell.setCellValue("姓名");
        cell.setCellStyle(style);
        cell = row.createCell(1);
        cell.setCellValue("部门");
        cell.setCellStyle(style);
        cell = row.createCell(2);
        cell.setCellValue("得分");
        cell.setCellStyle(style);
    }
    
    protected void buildExcelFile(String filename,HSSFWorkbook workbook) throws Exception{
        FileOutputStream fos = new FileOutputStream(filename);
        workbook.write(fos);
        fos.flush();
        fos.close();
    }
    
    protected void buildExcelDocument(String filename,HSSFWorkbook workbook,HttpServletResponse response) throws Exception{
        response.setContentType("application/vnd.ms-excel");
        response.setHeader("Content-Disposition", "attachment;filename="+URLEncoder.encode(filename, "utf-8"));
        OutputStream outputStream = response.getOutputStream();
        workbook.write(outputStream);
        outputStream.flush();
        outputStream.close();
    }
}
