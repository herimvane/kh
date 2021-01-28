package com.herim.kh.domain;

import java.time.LocalDateTime;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.ManyToOne;
import javax.persistence.OneToOne;

import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.GenericGenerator;

import lombok.Data;

@Data
@Entity(name = "assessment")
public class Assessment {

	@Id
	@GeneratedValue(generator = "uuid2")
    @GenericGenerator(name = "uuid2", strategy = "org.hibernate.id.UUIDGenerator")
	private String id;
	
	@ManyToOne
	@JoinColumn(name = "assesser_id")
	private User assesser;
	
	@OneToOne
	@JoinColumn(name="user_id")
	private User user;
	@OneToOne
	@JoinColumn(name="dept_id")
	private Dept dept;
	@ColumnDefault(value = "0")
	private Integer score;
	@Column(name = "finish_date")
	private LocalDateTime finishDate;
	
	private String type;//考核类型 A:部门负责人；B:其他科级干部；C:其他科级以下干部。
	
	private double weight;
	
	//部门得分权重
	private double weightDept;
	
	@Column(name = "user_dept_id")
	private String userDeptId;
}
