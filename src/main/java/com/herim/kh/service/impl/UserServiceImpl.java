package com.herim.kh.service.impl;

import java.text.Collator;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

import org.apache.shiro.crypto.hash.SimpleHash;
import org.apache.shiro.util.ByteSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import com.herim.kh.dao.AssessmentRepository;
import com.herim.kh.dao.PositionRepository;
import com.herim.kh.dao.UserRepository;
import com.herim.kh.domain.Assessment;
import com.herim.kh.domain.Position;
import com.herim.kh.domain.User;
import com.herim.kh.domain.UserScore;
import com.herim.kh.exceptionhandler.MyException;
import com.herim.kh.service.UserService;

import net.sourceforge.pinyin4j.PinyinHelper;

@Service
public class UserServiceImpl implements UserService {
	
	
	
	@Autowired
    private JdbcTemplate jdbcTemplate;
	
	@Autowired
	private UserRepository userRepository;
	
	@Autowired
	private PositionRepository positionRepository;
	
	@Autowired
	private AssessmentRepository assessmentRepository;
	
	
	
	private static final String JZ = "局长";
	private static final String QTJLD = "其他局领导";
	private static final String BMFZR = "部门负责人";
	private static final String QTKJGB = "其他科级干部";
	private static final String KJYXGB = "科级以下干部";
	
	private static final String JWBGS = "纪委办公室";
	
	//打分权重
	//1.对部门部门负责人考核
	private static final double $1_JZ_BMFZR = 0.4*0.3;//局长对部门负责人
	private static final double $1_QTJLD_BMFZR = 0.4*0.7;//其他局领导对部门负责人
	private static final double $1_QTKJGB_BMFZR = 0.2;//其他部门负责人对部门负责人
	private static final double $1_BBMQTGB_BMFZR = 0.2;//本部门其他干部对部门负责人
	private static final double $1_BMDF_BMFZR = 0.2;//部门得分对部门负责人
	
	//2.对纪委办公室负责人考核
	private static final double $2_SJJWBGJ_JWBGSFZR = 0.8;//省局纪委办公室反馈得分
	private static final double $2_JZ_JWBGSFZR = 0.06*0.3;//局长评分
	private static final double $2_QTJLD_JWBGSFZR = 0.06*0.7;//其他局领导评分
	private static final double $2_QTKJGB_JWBGSFZR = 0.04;//其他负责人评分
	private static final double $2_BBMQTGB_JWBGSFZR = 0.06;//本部门其他干部评分
	private static final double $2_BMDF_JWBGSFZR = 0.04;//部门得分
	
	/*
	//3.对其他科级干部考核
	private static final double $3_JZ_QTKJGB = 0.3*0.3;//局长打分
	private static final double $3_FGLD_QTKJGB = 0.3*0.4;//分管领导打分
	private static final double $3_QTJLD_QTKJGB = 0.3*0.3;//其他局领导打分
	private static final double $3_BMFZR_QTKJGB = 0.2*0.3;//部门负责人打分
	private static final double $3_QTKJGB_QTKJGB = 0.2*0.7;//其他科级干部打分
	private static final double $3_BBMQTGB_QTKJGB = 0.3;//本部门其他干部打分
	private static final double $3_BMDF_QTKJGB = 0.2;//部门得分
	
	//4.对纪委办公室其他科级干部考核
	private static final double $4_JZ_JWBGSQTKJGB = 0.5*0.3;//局领导打分
	private static final double $4_FGLD_JWBGSQTKJGB = 0.5*0.6;//分管领导打分
	private static final double $4_QTJLD_JWBGSQTKJGB = 0.5*0.1;//其他局领导打分
	private static final double $4_JWBGSBMFZR_JWBGSQTKJGB = 0.2;//负责人打分
	private static final double $4_QTKJGB_JWBGSQTKJGB = 0.1;//其他科级干部打分
	private static final double $4_BBMQTGB_JWBGSQTKJGB = 0.1;//部门其他干部打分
	private static final double $4_BMDF_JWBGSQTKJGB = 0.1;//部门得分
	*/
	
	
	//5.对机关其他干部的考核
	private static final double $5_FGLD_QTGB = 0.35;//分管领导
	private static final double $5_BMFZR_QTGB = 0.35;//部门负责人
	private static final double $5_BBMQTGB_QTGB = 0.3;//本部门其他干部
	
	//6.对监管组其他干部考核
	private static final double $6_FGLD_JGZQTGB = 0.35;//分管领导
	private static final double $6_BMFZR_JGZQTGB = 0.35;//部门负责人
	private static final double $6_FJZNBM_JGZQTGB = 0.3;//本部门其他干部
	
	
	
	@Override
	public User findByName(String name) {
		return userRepository.findByName(name);
	}
	
	@Override
	public User findById(String id) {
		return userRepository.getOne(id);
	}
	
	@Override
	public User addUser(User user) {
		String password = (new SimpleHash("MD5", user.getPassword(), ByteSource.Util.bytes("HERIMVANE"), 2)).toString();
		user.setPassword(password);
		user.setStatus(0);
		if (user.getDeptsInLeader() != null)
			if(user.getDeptsInLeader().get(0).getId().length()==0) user.setDeptsInLeader(null);
		if(user.getDept().getId().length()==0) user.setDept(null);
		if(user.getPosition().getId().length()==0) user.setPosition(null);
		user.setPassword(password);
		return userRepository.save(user);
	}
	
	@Override
	public List<User> findByPosition(Position position) {
		return userRepository.findByPosition(position);
	}
	
	@Override
	public void updateUserStatus(Integer status, String id) {
		userRepository.updateStatus(status, id);
	}
	
	/**
	 * 对部门负责人打分
	 * @param user
	 */
	private void generateAssessment4BMFZR(User user) {
		//1.对部门负责人的考核
		//获得所有部门负责人
		Position position_bmfzr = positionRepository.findByName(BMFZR);
		List<User> bmfzrs = findByPosition(position_bmfzr);
		for(User bmfzr : bmfzrs) {
			
			if(bmfzr.getName().equals(user.getName())) continue;//本人不打分
			if(isJZ(user) || isQTJDL(user) || isKJGB(user) || isBBMQTKJYXGB(bmfzr, user)) {//具有打分权限的人
				Assessment assessment = new Assessment();
				assessment.setAssesser(user);//设置打分人
				assessment.setUser(bmfzr);//设置被考核人
				assessment.setScore(0);
				assessment.setUserDeptId(bmfzr.getDept().getId());
				if(bmfzr.getDept().getName().equals(JWBGS)) {//纪委办公室负责人
					if(isJZ(user)) {
						assessment.setWeight($2_JZ_JWBGSFZR);//局长
						assessment.setType("A_JZ_JWBGSFZR");
					}
					else if(isQTJDL(user)) {
						assessment.setWeight($2_QTJLD_JWBGSFZR);//其他局领导
						assessment.setType("A_QTJLD_JWBGSFZR");
					}
					else if(isKJGB(user)) {
						assessment.setWeight($2_QTKJGB_JWBGSFZR);//其他科级干部
						assessment.setType("A_QTKJGB_JWBGSFZR");
					}
					else if(isBBMQTKJYXGB(bmfzr, user)) {
						assessment.setWeight($2_BBMQTGB_JWBGSFZR);//本部门其他科级以下干部
						assessment.setType("A_BBMQTGB_JWBGSFZR");
					}
					assessment.setWeightDept($2_BMDF_JWBGSFZR);
				} else {
					if(isJZ(user)) {
						assessment.setWeight($1_JZ_BMFZR);
						assessment.setType("A_JZ_BMFZR");
					}
					else if(isQTJDL(user)) {
						assessment.setWeight($1_QTJLD_BMFZR);
						assessment.setType("A_QTJLD_BMFZR");
					}
					else if(isKJGB(user)) {
						assessment.setWeight($1_QTKJGB_BMFZR);
						assessment.setType("A_QTKJGB_BMFZR");
					}
					else if(isBBMQTKJYXGB(bmfzr, user)) {
						assessment.setWeight($1_BBMQTGB_BMFZR);
						assessment.setType("A_BBMQTGB_BMFZR");
					}
					assessment.setWeightDept($1_BMDF_BMFZR);
				}
				assessmentRepository.save(assessment);
			}
		}
	}
	
	/**
	 * 对其他科级干部打分
	 * @param user
	 */
	/*private void generateAssessment4QTKJGB(User user) {
		//2.对其他科级干部的考核
		//获得所有其他科级干部
		Position position_qtkjgb = positionRepository.findByName(QTKJGB);
		List<User> qtkjgbs = findByPosition(position_qtkjgb);
		for(User qtkjgb : qtkjgbs) {
			if(qtkjgb.getName().equals(user.getName())) continue;
			if(isJZ(user) || isFGLD(user, qtkjgb) || isQTJDLNotFGLD(user, qtkjgb) || isKJGB(user) || isBBMQTKJYXGB(qtkjgb, user)) {//具有打分权限的人
				Assessment assessment = new Assessment();
				assessment.setAssesser(user);//设置打分人
				assessment.setUser(qtkjgb);//设置被考核人
				assessment.setScore(0);
				assessment.setUserDeptId(qtkjgb.getDept().getId());
				//
				
				Assessment assessment2 = new Assessment();
				assessment2.setAssesser(user);//设置打分人
				assessment2.setUser(qtkjgb);//设置被考核人
				assessment2.setScore(0);
				assessment2.setUserDeptId(qtkjgb.getDept().getId());
				
				//
				if(qtkjgb.getDept().getName().equals(JWBGS)) {//纪委办公室其他科级干部
					
					if(isJZ(user) && isFGLD(user, qtkjgb)) {
						assessment.setWeight($4_JZ_JWBGSQTKJGB);
						assessment.setType("B_JZ_JWBGSQTKJGB");
						assessment2.setWeight($4_FGLD_JWBGSQTKJGB);
						assessment2.setType("B_FGLD_JWBGSQTKJGB");
						assessmentRepository.save(assessment2);
					} else {
						if(isJZ(user)) {
							assessment.setWeight($4_JZ_JWBGSQTKJGB);
							assessment.setType("B_JZ_JWBGSQTKJGB");
						}
						if(isFGLD(user, qtkjgb)) {
							assessment.setWeight($4_FGLD_JWBGSQTKJGB);
							assessment.setType("B_FGLD_JWBGSQTKJGB");
						}
					}
					
					if(isQTJDLNotFGLD(user, qtkjgb)) {
						assessment.setWeight($4_QTJLD_JWBGSQTKJGB);
						assessment.setType("B_QQTJLD_JWBGSQTKJGB");
					}
					if(isBMFZR(user, qtkjgb)) {
						assessment.setWeight($4_JWBGSBMFZR_JWBGSQTKJGB);
						assessment.setType("B_JWBGSBMFZR_JWBGSQTKJGB");
					}
					if(isNotBBMFZR(user, qtkjgb)) {
						assessment.setWeight($4_QTKJGB_JWBGSQTKJGB);
						assessment.setType("B_QTKJGB_JWBGSQTKJGB");
					}
					if(isQTKJGB(user)) {
						assessment.setWeight($4_QTKJGB_JWBGSQTKJGB);
						assessment.setType("B_QTKJGB_JWBGSQTKJGB");
					}
					if(isBBMQTKJYXGB(qtkjgb, user)) {
						assessment.setWeight($4_BBMQTGB_JWBGSQTKJGB);
						assessment.setType("B_BBBMQTGB_JWBGSQTKJGB");
					}
					assessment.setWeightDept($4_BMDF_JWBGSQTKJGB);
				} else {
					
					if(isJZ(user) && isFGLD(user, qtkjgb)) {
						assessment.setWeight($3_JZ_QTKJGB);
						assessment.setType("B_JZ_QTKJGB");
						assessment2.setWeight($3_FGLD_QTKJGB);
						assessment2.setType("B_FGLD_QTKJGB");
						assessmentRepository.save(assessment2);
					} else {
						if(isJZ(user)) {
							assessment.setWeight($3_JZ_QTKJGB);
							assessment.setType("B_JZ_QTKJGB");
						}
						if(isFGLD(user, qtkjgb)) {
							assessment.setWeight($3_FGLD_QTKJGB);
							assessment.setType("B_FGLD_QTKJGB");
						}
					}
					if(isQTJDLNotFGLD(user, qtkjgb)) {
						assessment.setWeight($3_QTJLD_QTKJGB);
						assessment.setType("B_QTJLD_QTKJGB");
					}
					if(isBMFZR(user, qtkjgb)) {
						assessment.setWeight($3_BMFZR_QTKJGB);
						assessment.setType("B_BMFZR_QTKJGB");
					}
					if(isNotBBMFZR(user, qtkjgb)) {
						System.out.println(user.getName()+":"+qtkjgb.getName());
						assessment.setWeight($3_QTKJGB_QTKJGB);
						assessment.setType("B_QTKJGB_QTKJGB");
					}
					if(isQTKJGB(user)) {
						assessment.setWeight($3_QTKJGB_QTKJGB);
						assessment.setType("B_QTKJGB_QTKJGB");
					}
					if(isBBMQTKJYXGB(qtkjgb, user)) {
						assessment.setWeight($3_BBMQTGB_QTKJGB);
						assessment.setType("B_BBMQTGB_QTKJGB");
					
					}
					assessment.setWeightDept($3_BMDF_QTKJGB);
					
				}
				assessmentRepository.save(assessment);
			}
			
		}
	}*/
	
	/**
	 * 对其他科级以下干部打分
	 * @param user
	 */
	/*private void generateAssessment4QTKJYXGB(User user) {
		//3.对科级以下干部的考核
		//获得所有其他科级以下干部
		Position position_qtkjyxgb = positionRepository.findByName(KJYXGB);
		List<User> qtkjyxgbs = findByPosition(position_qtkjyxgb);
		for(User qtkjyxgb : qtkjyxgbs) {
			if(qtkjyxgb.getName().equals(user.getName())) continue;
			if(isFGLD(user, qtkjyxgb) || isBMFZR(user, qtkjyxgb) || isBBMGBNotFZR(qtkjyxgb, user)) {//具有打分权限的人
				Assessment assessment = new Assessment();
				assessment.setAssesser(user);//设置打分人
				assessment.setUser(qtkjyxgb);//设置被考核人
				assessment.setScore(0);
				assessment.setUserDeptId(qtkjyxgb.getDept().getId());
				if(isFGLD(user, qtkjyxgb)) {
					assessment.setWeight($5_FGLD_QTGB);
					assessment.setType("C_FGLD_QTGB");
				}
				if(isBMFZR(user, qtkjyxgb)) {
					assessment.setWeight($5_BMFZR_QTGB);
					assessment.setType("C_BMFZR_QTGB");
				}
				if(isBBMGBNotFZR(qtkjyxgb, user)) {
					assessment.setWeight($5_BBMQTGB_QTGB);
					assessment.setType("C_BBMQTGB_QTGB");
				}
				assessmentRepository.save(assessment);
			}
		}
	}*/
	
	/**
	 * 对其他干部打分
	 * @param user
	 */
	private void generateAssessment4QTGB(User user) {
		//科级以下干部
		Position position_qtkjyxgb = positionRepository.findByName(KJYXGB);
		List<User> qtkjyxgbs = findByPosition(position_qtkjyxgb);
		Iterator<User> iterator = qtkjyxgbs.iterator();
		while(iterator.hasNext()) {//去除监管组干部
			User u = iterator.next();
			if(u.getDept().getName().contains("监管组")) iterator.remove();
		}
		//其他科级干部
		Position position_qtkjgb = positionRepository.findByName(QTKJGB);
		List<User> qtkjgbs = findByPosition(position_qtkjgb);
		Iterator<User> iterator2 = qtkjgbs.iterator();
		while(iterator.hasNext()) {//去除监管组干部
			User u = iterator.next();
			if(u.getDept().getName().contains("监管组")) iterator2.remove();
		}
		qtkjyxgbs.addAll(qtkjgbs);
		
		for(User qtkjyxgb : qtkjyxgbs) {
			if(qtkjyxgb.getName().equals(user.getName())) continue;
			if(isFGLD(user, qtkjyxgb) || isBMFZR(user, qtkjyxgb) || isBBMGBNotFZR(qtkjyxgb, user)) {//具有打分权限的人
				Assessment assessment = new Assessment();
				assessment.setAssesser(user);//设置打分人
				assessment.setUser(qtkjyxgb);//设置被考核人
				assessment.setScore(0);
				assessment.setUserDeptId(qtkjyxgb.getDept().getId());
				if(isFGLD(user, qtkjyxgb)) {
					assessment.setWeight($5_FGLD_QTGB);
					assessment.setType("B_FGLD_QTGB");
				}
				if(isBMFZR(user, qtkjyxgb)) {
					assessment.setWeight($5_BMFZR_QTGB);
					assessment.setType("B_BMFZR_QTGB");
				}
				if(isBBMGBNotFZR(qtkjyxgb, user)) {
					assessment.setWeight($5_BBMQTGB_QTGB);
					assessment.setType("B_BBMQTGB_QTGB");
				}
				assessmentRepository.save(assessment);
			}
		}
	}
	
	/**
	 * 对其监管组干部打分
	 * @param user
	 */
	private void generateAssessment4JGZQTGB(User user) {
		//科级以下干部
		Position position_qtkjyxgb = positionRepository.findByName(KJYXGB);
		List<User> qtkjyxgbs = findByPosition(position_qtkjyxgb);
		Iterator<User> iterator = qtkjyxgbs.iterator();
		while(iterator.hasNext()) {//去除非监管组干部
			User u = iterator.next();
			if(!u.getDept().getName().contains("监管组")) iterator.remove();
		}
		//其他科级干部
		Position position_qtkjgb = positionRepository.findByName(QTKJGB);
		List<User> qtkjgbs = findByPosition(position_qtkjgb);
		Iterator<User> iterator2 = qtkjgbs.iterator();
		while(iterator2.hasNext()) {//去除非监管组干部
			User u = iterator2.next();
			if(!u.getDept().getName().contains("监管组")) iterator2.remove();
		}
		qtkjyxgbs.addAll(qtkjgbs);
		
		for(User qtkjyxgb : qtkjyxgbs) {
			if(qtkjyxgb.getName().equals(user.getName())) continue;
			if(isFGLD(user, qtkjyxgb) || isBMFZR(user, qtkjyxgb) || isFJDWZNBMFZR(user)) {//具有打分权限的人
				Assessment assessment = new Assessment();
				assessment.setAssesser(user);//设置打分人
				assessment.setUser(qtkjyxgb);//设置被考核人
				assessment.setScore(0);
				assessment.setUserDeptId(qtkjyxgb.getDept().getId());
				if(isFGLD(user, qtkjyxgb)) {
					assessment.setWeight($6_FGLD_JGZQTGB);
					assessment.setType("C_FGLD_JGZQTGB");
				}
				if(isBMFZR(user, qtkjyxgb)) {
					assessment.setWeight($6_BMFZR_JGZQTGB);
					assessment.setType("C_BMFZR_JGZQTGB");
				}
				if(isFJDWZNBMFZR(user)) {
					assessment.setWeight($6_FJZNBM_JGZQTGB);
					assessment.setType("C_FJZNBM_JGZQTGB");
				}
				assessmentRepository.save(assessment);
			}
		}
	}
	
	/**
	 * 生成打分
	 */
	@Override
	@Transactional(isolation= Isolation.DEFAULT,propagation= Propagation.REQUIRED,rollbackFor = Exception.class)
	public void generateMyAssessment(User user) throws MyException {
		try {
			if(user.getStatus()!=0) return;
			generateAssessment4BMFZR(user);
			generateAssessment4QTGB(user);
			generateAssessment4JGZQTGB(user);
			updateUserStatus(1, user.getId());
		} catch (Exception e) {
			e.printStackTrace();
			throw new MyException("系统错误，无法生成考核任务，稍后重试。");
		}
	}
	
	@Override
	@Transactional(isolation= Isolation.DEFAULT,propagation= Propagation.REQUIRED,rollbackFor = Exception.class)
	public void generateMyAssessment() throws MyException {
		try {
			List<User> users = userRepository.findAll();
			for(User user : users) {
				generateAssessment4BMFZR(user);
				generateAssessment4QTGB(user);
				generateAssessment4JGZQTGB(user);
				updateUserStatus(1, user.getId());
			}
		} catch (Exception e) {
			e.printStackTrace();
			throw new MyException("系统错误，无法生成考核任务，稍后重试。");
		}
	}
	
	/**
	 * 打分
	 */
	@Transactional
	@Override
	public void rating(Assessment assessment) {
		LocalDateTime now = LocalDateTime.now();
		now.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
		//assessmentRepository.updateScoreAndFinshDate(assessment.getScore(), now, assessment.getId());
		Assessment old = assessmentRepository.getOne(assessment.getId());
		old.setScore(assessment.getScore());
		old.setFinishDate(now);
		userRepository.updateStatus(3, old.getAssesser().getId());
	}
	
	/**
	 * 计算所有人得分
	 */
	@Override
	public List<UserScore> calculateAllUsersScore(double sjdf) {
		List<AssessmentRepository.NameOnly> list = assessmentRepository.calculateScore();
		List<UserScore> userScores = new ArrayList<UserScore>();
		for(AssessmentRepository.NameOnly obj : list) {
			User user = findById(obj.getUserid());
			UserScore us = new UserScore();
			us.setUser(user);
			us.setFinalScore(obj.getFinalscore());
			//计算纪委办公室负责人打分
			if(JWBGS.equals(user.getDept().getName()) && BMFZR.equals(user.getPosition().getName())){
				us.setFinalScore(obj.getFinalscore()+sjdf*$2_SJJWBGJ_JWBGSFZR);
			}
			//部门只有一个负责人
			if("李继明".equals(user.getName()) || "黄山".equals(user.getName()) || "邓学刚".equals(user.getName()) ) {
				us.setFinalScore(obj.getFinalscore()+95*0.2);
			}
			//部门只有一个其他干部
			/*if("杨杰".equals(user.getName()) || "杨波".equals(user.getName()) || "张洪".equals(user.getName()) ||"赵二佳".equals(user.getName())) {
				us.setFinalScore(obj.getFinalscore()+95*0.3);
			}*/
			userScores.add(us);
		}
		Collections.sort(userScores, new Comparator<UserScore>() {
			@Override
			public int compare(UserScore o1, UserScore o2) {
				return (int) (o2.getFinalScore()-o1.getFinalScore());
			}
		});
		return userScores;
	}
	
	@Transactional
	@Override
	public void changeMyPassword(String id ,String password) {
		userRepository.updatePassword(id ,password);
	}
	
	@Override
	public List<Assessment> findMyAssessments(User user) {
		return assessmentRepository.findByAssesser(user);
	}
	
	@Override
	public List<Assessment> findMyAssessmentsByType(User user, String type) {
		List<Assessment> assessments =  assessmentRepository.findByUserAndType(user.getId(), type);
		
		Collections.sort(assessments, new Comparator<Assessment>() {
			@Override
			public int compare(Assessment o1, Assessment o2) {
				String x1 = PinyinHelper.toHanyuPinyinStringArray(o1.getUser().getName().charAt(0))[0];
				String x2 = PinyinHelper.toHanyuPinyinStringArray(o2.getUser().getName().charAt(0))[0];
				System.out.println(x1+"--"+x2);
				return x1.compareTo(x2);
			}
		});
		return assessments;
	}
	
	//是否为局长
	private boolean isJZ(User user) {
		if(JZ.equals(user.getPosition().getName())) return true;else return false;
	}
	
	
	//是否为其他局领导
	private boolean isQTJDL(User user) {
		if(QTJLD.equals(user.getPosition().getName())) return true;else return false;
	}
	
	//是否为分管领导
	private boolean isFGLD(User leader, User user) {
		if(user.getDept().getLeader()==null) return false;
		if(user.getDept().getLeader().getName().equals(leader.getName())) return true;else return false;
	}
	//是否为其他局领导且不为分管领导
	private boolean isQTJDLNotFGLD(User leader, User user) {
		if(user.getDept().getLeader()==null) return false;
		if(!user.getDept().getLeader().getName().equals(leader.getName()) && QTJLD.equals(leader.getPosition().getName())) return true; else return false;
	}
		
	
	//是否为科级干部
	private boolean isKJGB(User user) {
		if(user.getPosition().getName().equals(QTKJGB) || user.getPosition().getName().equals(BMFZR)) return true;else return false;
	}
	
	//是否为科级干部且不为为本部门负责人
	private boolean isNotBBMFZR(User assesser,User user) {
		if(assesser.getPosition().getName().equals(BMFZR) && !user.getDept().getName().equals(assesser.getDept().getName())) return true;else return false;
	}
	
	//是否为其他科级干部且不是部门负责人
	private boolean isQTKJGB(User user) {
		if(user.getPosition().getName().equals(QTKJGB)) return true;else return false;
	}
	
	//是否为部门负责人
	private boolean isBMFZR(User charger, User user) {
		if(charger.getPosition().getName().equals(BMFZR) && user.getDept().getName().equals(charger.getDept().getName())) return true;else return false;
	}
	
	//是否为科级以下干部
	private boolean isKJYXGB(User user) {
		if(user.getPosition().getName().equals(KJYXGB)) return true;else return false;
	}
	
	//是否为本部门其他科级以下干部
	private boolean isBBMQTKJYXGB(User me, User other) {
		if(other.getDept()==null) return false;
		if(KJYXGB.equals(other.getPosition().getName()) && other.getDept().getName().equals(me.getDept().getName())) return true;else return false;
	}
	
	//是否为本部门除负责人以外干部
	private boolean isBBMGBNotFZR(User me, User other) {
		if(other.getDept()==null) return false;
		if(!BMFZR.equals(other.getPosition().getName()) && other.getDept().getName().equals(me.getDept().getName())) return true;else return false;
	}
	
	//是否为分局党委职能部门负责人，即人事科、纪委办公室、办公室负责人
	private boolean isFJDWZNBMFZR(User user) {
		if(user.getPosition().getName().equals(BMFZR)) {
			if(user.getDept().getName().equals("人事科")) return true;
			if(user.getDept().getName().equals("纪委办公室")) return true;
			if(user.getDept().getName().equals("办公室")) return true;
		}
		return false;
	}
	

}
